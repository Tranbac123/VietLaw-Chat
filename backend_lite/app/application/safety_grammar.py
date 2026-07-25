"""Bounded compositional grammar for five owner-approved safety families."""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import Literal

from .safety_registry import (
    ATOM_RULES,
    OPERATOR_RULES,
    HarmFamily,
    harm_rule_for_family,
)

ActorOrientation = Literal["USER", "THIRD_PARTY", "VICTIM_USER", "UNKNOWN"]


@dataclass(frozen=True, slots=True)
class ConceptAtom:
    kind: str
    name: str
    rule_id: str
    matched_span: tuple[int, int]
    lexeme: str


@dataclass(frozen=True, slots=True)
class OperatorSignal:
    kind: str
    name: str
    rule_id: str
    matched_span: tuple[int, int]
    lexeme: str


@dataclass(frozen=True, slots=True)
class ComposedHarm:
    family: HarmFamily
    stable_rule_id: str
    reason_code: str
    canonical_concept: str
    matched_span: tuple[int, int]


@dataclass(frozen=True, slots=True)
class ClauseGrammar:
    folded_text: str
    actor_orientation: ActorOrientation
    atoms: tuple[ConceptAtom, ...]
    operators: tuple[OperatorSignal, ...]
    harm_concepts: tuple[ComposedHarm, ...]
    direct_operators: tuple[OperatorSignal, ...]
    application_operators: tuple[OperatorSignal, ...]
    concealment_operators: tuple[OperatorSignal, ...]
    context_operators: tuple[OperatorSignal, ...]
    target_families: tuple[HarmFamily, ...]
    quoted: bool
    personal_police_contact: bool
    direct_harm: bool
    safe_prevention: bool
    victim_reporting: bool
    lawful_compliance: bool
    descriptive: bool
    safe_negation: bool


_QUOTE_MARKS = ('"', "'", "“", "”", "‘", "’")
_WORD_EDGE_LEFT = r"(?<![0-9a-zA-Z_])"
_WORD_EDGE_RIGHT = r"(?![0-9a-zA-Z_])"


def fold_text(value: str) -> str:
    """Return one canonical case/diacritic-folded representation."""

    decomposed = unicodedata.normalize("NFD", value.casefold().replace("đ", "d"))
    return "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )


def _find_lexeme(text: str, lexeme: str) -> tuple[int, int] | None:
    pattern = re.compile(
        _WORD_EDGE_LEFT + re.escape(lexeme) + _WORD_EDGE_RIGHT,
        re.IGNORECASE,
    )
    match = pattern.search(text)
    return match.span() if match else None


def _match_atoms(folded: str, clause_start: int) -> tuple[ConceptAtom, ...]:
    matches: list[ConceptAtom] = []
    for rule in ATOM_RULES:
        candidates: list[tuple[int, int, int, str]] = []
        for order, lexeme in enumerate(rule.lexemes):
            span = _find_lexeme(folded, lexeme)
            if span is not None:
                candidates.append((span[0], order, span[1], lexeme))
        if not candidates:
            continue
        start, _, end, lexeme = min(candidates)
        matches.append(
            ConceptAtom(
                rule.kind,
                rule.name,
                rule.rule_id,
                (clause_start + start, clause_start + end),
                lexeme,
            )
        )
    return tuple(matches)


def _match_operators(folded: str, clause_start: int) -> tuple[OperatorSignal, ...]:
    matches: list[OperatorSignal] = []
    for rule in OPERATOR_RULES:
        candidates: list[tuple[int, int, int, str]] = []
        for order, lexeme in enumerate(rule.lexemes):
            span = _find_lexeme(folded, lexeme)
            if span is not None:
                candidates.append((span[0], order, span[1], lexeme))
        if not candidates:
            continue
        start, _, end, lexeme = min(candidates)
        matches.append(
            OperatorSignal(
                rule.kind,
                rule.name,
                rule.rule_id,
                (clause_start + start, clause_start + end),
                lexeme,
            )
        )
    return tuple(matches)


def _named(atoms: tuple[ConceptAtom, ...], kind: str, names: tuple[str, ...]) -> bool:
    return any(atom.kind == kind and atom.name in names for atom in atoms)


def _has_lexeme(
    atoms: tuple[ConceptAtom, ...],
    kind: str,
    name: str,
    lexemes: tuple[str, ...],
) -> bool:
    return any(
        atom.kind == kind and atom.name == name and atom.lexeme in lexemes
        for atom in atoms
    )


def _operators(
    operators: tuple[OperatorSignal, ...],
    kinds: tuple[str, ...],
) -> tuple[OperatorSignal, ...]:
    return tuple(operator for operator in operators if operator.kind in kinds)


def _harm_span(atoms: tuple[ConceptAtom, ...], clause_start: int) -> tuple[int, int]:
    semantic = tuple(atom for atom in atoms if atom.kind != "actor")
    if not semantic:
        return (clause_start, clause_start)
    return (
        min(atom.matched_span[0] for atom in semantic),
        max(atom.matched_span[1] for atom in semantic),
    )


def _compose_harm(
    atoms: tuple[ConceptAtom, ...],
    folded: str,
    clause_start: int,
) -> tuple[ComposedHarm, ...]:
    def action(*names: str) -> bool:
        return _named(atoms, "action", tuple(names))

    def obj(*names: str) -> bool:
        return _named(atoms, "object", tuple(names))

    def objective(*names: str) -> bool:
        return _named(atoms, "objective", tuple(names))

    def actor(*names: str) -> bool:
        return _named(atoms, "actor", tuple(names))

    third_party_avoidance = action("help") and actor("third_party") and (
        obj("required_appearance") or objective("avoid_appearance")
    )
    evasion = not third_party_avoidance and (
        action("evade")
        and (
            obj("police_authority", "required_appearance")
            or objective("avoid_appearance", "prevent_discovery", "avoid_detection")
        )
        or action("delay")
        and obj("police_authority")
        and objective("prevent_discovery", "avoid_detection")
        or obj("police_authority") and objective("prevent_discovery")
    )
    forgery = action("forge") or (
        action("alter", "fabricate")
        and obj("document")
        and objective("appear_authentic", "pass_inspection", "false_content")
    ) or obj("document") and objective("appear_authentic") and objective(
        "false_content"
    )
    evasion = evasion or not third_party_avoidance and _has_lexeme(
        atoms,
        "action",
        "evade",
        ("ne", "tron", "lan tranh", "lan tron", "tranh mat", "thoat khoi"),
    )
    evidence_destruction = (
        action("delete", "destroy", "hide")
        and obj("evidence", "camera_data", "message")
    ) or (
        action("disable")
        and obj("evidence", "camera_data")
        and (
            objective("unusable", "prevent_recording", "prevent_discovery")
            or obj("police_authority")
        )
    ) or (
        obj("evidence", "camera_data")
        and objective("unusable", "leave_no_trace")
    )
    property_coercion = action("detain") and obj("person", "debtor", "property") and (
        objective("force_payment") or obj("debtor") or action("coerce")
    )
    coercion = not property_coercion and (
        action("threaten") and (obj("person", "debtor") or actor("victim_user"))
        or action("coerce")
        or action("frighten")
        and obj("person")
        and objective("frighten_person", "force_payment")
    )
    obstruction = (
        action("obstruct") and obj("investigation", "police_authority")
        or action("provide_information")
        and objective("false_content", "delay_investigation")
        and (obj("information", "investigation") or objective("delay_investigation"))
        or action("distort") and obj("investigation")
        or action("hide") and obj("person") and objective("wanted_person")
        or third_party_avoidance
    )

    span = _harm_span(atoms, clause_start)
    composed: list[ComposedHarm] = []
    for family, enabled, property_variant in (
        ("EVASION", evasion, False),
        ("FORGERY", forgery, False),
        ("EVIDENCE_DESTRUCTION", evidence_destruction, False),
        ("COERCION_OR_THREAT", coercion, False),
        ("OBSTRUCTION", obstruction, False),
        ("COERCION_OR_THREAT", property_coercion, True),
    ):
        if not enabled:
            continue
        rule = harm_rule_for_family(family, property_coercion=property_variant)
        composed.append(
            ComposedHarm(
                rule.family,
                rule.rule_id,
                rule.reason_code,
                rule.canonical_concept,
                span,
            )
        )
    return tuple(composed)


def _actor_orientation(
    atoms: tuple[ConceptAtom, ...],
    operators: tuple[OperatorSignal, ...],
    harms: tuple[ComposedHarm, ...],
) -> ActorOrientation:
    if _named(atoms, "actor", ("victim_user",)):
        return "VICTIM_USER"
    harm_start = min((harm.matched_span[0] for harm in harms), default=10**9)
    third_party = tuple(
        atom for atom in atoms if atom.kind == "actor" and atom.name == "third_party"
    )
    if third_party and _operators(operators, ("prevention",)):
        return "THIRD_PARTY"
    if any(atom.matched_span[0] <= harm_start for atom in third_party):
        return "THIRD_PARTY"
    if _named(atoms, "actor", ("user",)) or _operators(
        operators,
        ("direct", "application"),
    ):
        return "USER"
    return "UNKNOWN"


def _last_start(operators: tuple[OperatorSignal, ...], kinds: tuple[str, ...]) -> int:
    starts = tuple(
        operator.matched_span[0] for operator in operators if operator.kind in kinds
    )
    return max(starts, default=-1)


def _direct_linked(
    folded: str,
    actor: ActorOrientation,
    harms: tuple[ComposedHarm, ...],
    operators: tuple[OperatorSignal, ...],
    safe_prevention: bool,
    victim_reporting: bool,
    descriptive: bool,
) -> bool:
    if not harms:
        return False
    concealment = bool(_operators(operators, ("concealment",)))
    application = bool(_operators(operators, ("application",)))
    if concealment or application:
        return True

    direct = _operators(operators, ("direct",))
    method = _operators(operators, ("method",))
    direct_start = _last_start(operators, ("direct", "method"))
    safe_start = _last_start(
        operators,
        ("reporting", "prevention", "preservation", "detection", "safe_negation"),
    )
    safe_ends = tuple(
        operator.matched_span[1]
        for operator in operators
        if operator.kind
        in {"reporting", "prevention", "preservation", "detection", "safe_negation"}
    )
    safe_end = max(safe_ends, default=-1)
    direct_targets_safe_operator = safe_start > direct_start >= 0
    method_surface = folded.lstrip().startswith(("cach ", "phuong phap ")) or any(
        operator.lexeme in {"the nao", "bang cach nao", "tung buoc"}
        and operator.matched_span[0] >= harms[0].matched_span[0]
        for operator in method
    )
    explicit = bool(direct) or method_surface
    description_start = _last_start(operators, ("description",))
    if descriptive and description_start >= 0 and description_start < direct_start:
        if not any(marker in folded for marker in ("toi muon", "chi toi", "giup toi")):
            explicit = False
    imperative_obstruction = folded.lstrip().startswith(("can tro ", "ngan can "))
    method_targets_reporting = bool(victim_reporting and not direct and method)
    direct_inside_safe_operator = safe_start >= 0 and direct_start < safe_end
    if (
        direct_targets_safe_operator
        or method_targets_reporting
        or safe_prevention and direct_inside_safe_operator
    ) and not application:
        explicit = False
    if (safe_prevention or victim_reporting or descriptive) and not explicit:
        return imperative_obstruction
    if actor == "THIRD_PARTY" and not explicit:
        return False
    return explicit or imperative_obstruction


def analyze_clause_grammar(
    normalized_text: str,
    clause_start: int,
) -> ClauseGrammar:
    """Resolve atoms, operators, targets, and local intent for one clause."""

    folded = fold_text(normalized_text)
    atoms = _match_atoms(folded, clause_start)
    operators = _match_operators(folded, clause_start)
    harms = _compose_harm(atoms, folded, clause_start)
    actor = _actor_orientation(atoms, operators, harms)
    quoted = any(mark in normalized_text for mark in _QUOTE_MARKS)
    applications = _operators(operators, ("application",))
    concealments = _operators(operators, ("concealment",))

    safe_negation = bool(_operators(operators, ("safe_negation",))) and not bool(
        concealments
    ) and any(
        phrase in folded
        for phrase in (
            "toi khong muon",
            "toi khong dinh",
            "lam sao de khong",
            "lam the nao de khong",
            "tranh vo tinh",
            "can tranh",
            "tranh lam mat",
        )
    )
    prevention_ops = _operators(operators, ("prevention",))
    preservation_ops = _operators(operators, ("preservation",))
    detection_ops = _operators(operators, ("detection",))
    safe_prevention = bool(
        safe_negation
        or prevention_ops
        and actor in {"THIRD_PARTY", "VICTIM_USER"}
        or preservation_ops
        and _named(atoms, "object", ("evidence", "camera_data", "message", "document"))
        or detection_ops
        and _named(atoms, "object", ("document", "evidence", "camera_data"))
    ) and not bool(concealments)
    reporting_ops = _operators(operators, ("reporting",))
    victim_reporting = bool(
        actor in {"THIRD_PARTY", "VICTIM_USER"} and harms
        or reporting_ops and (harms or actor in {"THIRD_PARTY", "VICTIM_USER"})
        or "nguoi tu xung" in folded
        and _named(atoms, "object", ("police_authority",))
    )
    if actor == "VICTIM_USER" and safe_prevention:
        victim_reporting = False
    compliance_ops = _operators(operators, ("compliance",))
    police_contact_ops = _operators(operators, ("police_contact",))
    has_police_target = _named(
        atoms,
        "object",
        ("police_authority", "required_appearance", "official_notice"),
    )
    outbound_reporting = bool(
        _operators(operators, ("reporting",))
        and "lien he co quan chuc nang" in folded
    )
    personal_police_contact = bool(
        has_police_target
        and police_contact_ops
        and not outbound_reporting
        and (
            "toi" in folded
            or _named(atoms, "object", ("police_authority",))
        )
        or "lam viec voi cong an" in folded
        or "toi" in folded
        and compliance_ops
        and _named(atoms, "object", ("official_notice",))
    )
    lawful_compliance = bool(
        (
            has_police_target
            or _named(atoms, "object", ("investigation",))
        )
        and compliance_ops
        or personal_police_contact
    )
    description_ops = _operators(operators, ("description",))
    descriptive = bool((description_ops or quoted) and harms and not applications)

    direct = _direct_linked(
        folded,
        actor,
        harms,
        operators,
        safe_prevention,
        victim_reporting,
        descriptive,
    )
    context = _operators(
        operators,
        (
            "reporting",
            "prevention",
            "preservation",
            "detection",
            "compliance",
            "description",
            "safe_negation",
        ),
    )
    direct_operators = _operators(operators, ("direct", "method"))
    return ClauseGrammar(
        folded,
        actor,
        atoms,
        operators,
        harms,
        direct_operators,
        applications,
        concealments,
        context,
        tuple(harm.family for harm in harms),
        quoted,
        personal_police_contact,
        direct,
        safe_prevention,
        victim_reporting,
        lawful_compliance,
        descriptive,
        safe_negation,
    )


__all__ = [
    "ActorOrientation",
    "ClauseGrammar",
    "ComposedHarm",
    "ConceptAtom",
    "OperatorSignal",
    "analyze_clause_grammar",
    "fold_text",
]
