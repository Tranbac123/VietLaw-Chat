"""Canonical immutable registries for the bounded deterministic safety policy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

HarmFamily = Literal[
    "EVASION",
    "FORGERY",
    "EVIDENCE_DESTRUCTION",
    "COERCION_OR_THREAT",
    "OBSTRUCTION",
]


@dataclass(frozen=True, slots=True)
class HarmRuleSpec:
    family: HarmFamily
    rule_id: str
    reason_code: str
    canonical_concept: str


@dataclass(frozen=True, slots=True)
class RiskRuleSpec:
    rule_id: str
    reason_code: str


@dataclass(frozen=True, slots=True)
class AtomRuleSpec:
    kind: Literal["action", "object", "objective", "actor"]
    name: str
    rule_id: str
    lexemes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OperatorRuleSpec:
    kind: Literal[
        "direct",
        "method",
        "application",
        "concealment",
        "reporting",
        "prevention",
        "preservation",
        "detection",
        "compliance",
        "description",
        "safe_negation",
        "police_contact",
    ]
    name: str
    rule_id: str
    lexemes: tuple[str, ...]


# Owner order is policy authority and must not be derived from mapping iteration.
HARM_RULES = (
    HarmRuleSpec(
        "EVASION",
        "safety.evasion.v1",
        "HARM_EVASION",
        "evade_authorities_or_required_appearance",
    ),
    HarmRuleSpec(
        "FORGERY",
        "safety.forgery.v1",
        "HARM_FORGERY",
        "forge_or_deceptively_alter_documents",
    ),
    HarmRuleSpec(
        "EVIDENCE_DESTRUCTION",
        "safety.evidence_destruction.v1",
        "HARM_EVIDENCE_DESTRUCTION",
        "destroy_conceal_or_disable_evidence",
    ),
    HarmRuleSpec(
        "COERCION_OR_THREAT",
        "safety.coercion.v1",
        "HARM_COERCION_OR_THREAT",
        "coerce_or_threaten_for_payment",
    ),
    HarmRuleSpec(
        "OBSTRUCTION",
        "safety.obstruction.v1",
        "HARM_OBSTRUCTION",
        "obstruct_or_deceptively_delay_investigation",
    ),
    HarmRuleSpec(
        "COERCION_OR_THREAT",
        "safety.property_coercion.v1",
        "HARM_COERCION_OR_THREAT",
        "hold_person_or_property_to_coerce_payment",
    ),
)

RISK_RULES = (
    RiskRuleSpec("risk.police_contact.v1", "RISK_POLICE_CONTACT"),
    RiskRuleSpec(
        "risk.serious_accident.v1",
        "RISK_SERIOUS_OR_FATAL_ACCIDENT",
    ),
    RiskRuleSpec(
        "risk.threat_received.v1",
        "RISK_VIOLENCE_OR_THREAT_RECEIVED",
    ),
    RiskRuleSpec(
        "risk.property_seizure.v1",
        "RISK_PROPERTY_SEIZURE_OR_COERCION",
    ),
    RiskRuleSpec("risk.criminal_exposure.v1", "RISK_CRIMINAL_EXPOSURE"),
)

SAFE_CONTEXT_RULES = (
    "safety.context.safe_negation.v1",
    "safety.context.victim_reporting.v1",
    "safety.context.prevention_protection.v1",
    "safety.context.lawful_compliance.v1",
    "safety.context.descriptive_quoted.v1",
)

SAFETY_REASON_CODES = (
    "HARM_EVASION",
    "HARM_FORGERY",
    "HARM_EVIDENCE_DESTRUCTION",
    "HARM_COERCION_OR_THREAT",
    "HARM_OBSTRUCTION",
    "RISK_POLICE_CONTACT",
    "RISK_SERIOUS_OR_FATAL_ACCIDENT",
    "RISK_VIOLENCE_OR_THREAT_RECEIVED",
    "RISK_PROPERTY_SEIZURE_OR_COERCION",
    "RISK_CRIMINAL_EXPOSURE",
)

INTENT_OPERATOR_IDS = (
    "safety.intent.direct_assistance.v1",
    "safety.intent.method_request.v1",
    "safety.intent.application.v1",
    "safety.intent.immediate_anaphora.v1",
)

CONCEALMENT_OPERATOR_IDS = ("safety.intent.concealment.v1",)
POLICE_CONTACT_IDS = ("risk.police_contact.v1",)


# Lexemes are folded canonical forms. They are semantic atoms, not complete
# prompt strings. A harm family is resolved only by approved atom composition.
ATOM_RULES = (
    AtomRuleSpec(
        "action",
        "evade",
        "safety.atom.action.evade.v1",
        (
            "ne",
            "tron",
            "lan tranh",
            "lan tron",
            "tranh mat",
            "tranh",
            "thoat khoi",
        ),
    ),
    AtomRuleSpec(
        "action",
        "delay",
        "safety.atom.action.delay.v1",
        ("tri hoan", "cau gio", "keo dai", "lam cham"),
    ),
    AtomRuleSpec(
        "action",
        "forge",
        "safety.atom.action.forge.v1",
        ("lam gia", "gia mao", "nguy tao", "che tao", "gia"),
    ),
    AtomRuleSpec(
        "action",
        "alter",
        "safety.atom.action.alter.v1",
        ("chinh sua", "sua", "tay sua", "thay doi", "khien", "lam"),
    ),
    AtomRuleSpec(
        "action",
        "fabricate",
        "safety.atom.action.fabricate.v1",
        ("tao", "che", "dung"),
    ),
    AtomRuleSpec(
        "action",
        "delete",
        "safety.atom.action.delete.v1",
        ("xoa bo", "xoa sach", "xoa het", "xoa"),
    ),
    AtomRuleSpec(
        "action",
        "destroy",
        "safety.atom.action.destroy.v1",
        ("pha huy", "tieu huy", "dot", "lam mat", "huy"),
    ),
    AtomRuleSpec(
        "action",
        "disable",
        "safety.atom.action.disable.v1",
        ("vo hieu hoa", "lam hong", "khien", "ngan"),
    ),
    AtomRuleSpec(
        "action",
        "hide",
        "safety.atom.action.hide.v1",
        ("che giau", "giau", "an nap"),
    ),
    AtomRuleSpec(
        "action",
        "threaten",
        "safety.atom.action.threaten.v1",
        ("de doa", "uy hiep", "doa"),
    ),
    AtomRuleSpec(
        "action",
        "frighten",
        "safety.atom.action.frighten.v1",
        ("lam cho", "lam", "khien"),
    ),
    AtomRuleSpec(
        "action",
        "coerce",
        "safety.atom.action.coerce.v1",
        ("cuong ep", "khong che", "ep", "buoc ho", "buoc nguoi"),
    ),
    AtomRuleSpec(
        "action",
        "detain",
        "safety.atom.action.detain.v1",
        ("chiem giu", "bat giu", "giu", "siet"),
    ),
    AtomRuleSpec(
        "action",
        "obstruct",
        "safety.atom.action.obstruct.v1",
        ("can tro", "ngan can", "pha roi"),
    ),
    AtomRuleSpec(
        "action",
        "provide_information",
        "safety.atom.action.provide_information.v1",
        ("cung cap", "dua", "khai", "bao"),
    ),
    AtomRuleSpec(
        "action",
        "distort",
        "safety.atom.action.distort.v1",
        ("lam sai lech", "boi sai", "lam lech"),
    ),
    AtomRuleSpec(
        "action",
        "help",
        "safety.atom.action.help.v1",
        ("giup", "ho tro"),
    ),
    AtomRuleSpec(
        "object",
        "police_authority",
        "safety.atom.object.police_authority.v1",
        (
            "co quan dieu tra",
            "dieu tra vien",
            "cong an",
            "canh sat",
            "co quan chuc nang",
        ),
    ),
    AtomRuleSpec(
        "object",
        "required_appearance",
        "safety.atom.object.required_appearance.v1",
        (
            "yeu cau len lam viec",
            "len lam viec",
            "giay trieu tap",
            "trieu tap",
            "trinh dien",
            "buoi lam viec",
        ),
    ),
    AtomRuleSpec(
        "object",
        "document",
        "safety.atom.object.document.v1",
        (
            "giay to",
            "tai lieu",
            "van ban",
            "ho so",
            "giay moi",
            "giay trieu tap",
            "ban chinh",
        ),
    ),
    AtomRuleSpec(
        "object",
        "official_notice",
        "safety.atom.object.official_notice.v1",
        ("giay moi", "giay trieu tap", "thong bao"),
    ),
    AtomRuleSpec(
        "object",
        "evidence",
        "safety.atom.object.evidence.v1",
        ("chung cu", "bang chung", "dau vet", "du lieu dieu tra"),
    ),
    AtomRuleSpec(
        "object",
        "camera_data",
        "safety.atom.object.camera_data.v1",
        ("du lieu camera", "camera", "ghi hinh", "video", "du lieu"),
    ),
    AtomRuleSpec(
        "object",
        "message",
        "safety.atom.object.message.v1",
        ("tin nhan", "thu dien tu", "email", "tep tin", "file"),
    ),
    AtomRuleSpec(
        "object",
        "investigation",
        "safety.atom.object.investigation.v1",
        ("qua trinh dieu tra", "viec dieu tra", "dieu tra", "thi hanh"),
    ),
    AtomRuleSpec(
        "object",
        "information",
        "safety.atom.object.information.v1",
        ("thong tin", "loi khai", "noi dung"),
    ),
    AtomRuleSpec(
        "object",
        "person",
        "safety.atom.object.person.v1",
        ("nguoi khac", "nguoi kia", "mot nguoi", "ho", "nguoi"),
    ),
    AtomRuleSpec(
        "object",
        "debtor",
        "safety.atom.object.debtor.v1",
        ("con no", "nguoi no", "ben no"),
    ),
    AtomRuleSpec(
        "object",
        "property",
        "safety.atom.object.property.v1",
        ("tai san", "do dac", "xe", "hang hoa"),
    ),
    AtomRuleSpec(
        "objective",
        "appear_authentic",
        "safety.atom.objective.appear_authentic.v1",
        (
            "giong ban that",
            "giong ban chinh",
            "giong that",
            "trong nhu that",
            "trong that",
            "co ve that",
            "trong hop le",
        ),
    ),
    AtomRuleSpec(
        "objective",
        "pass_inspection",
        "safety.atom.objective.pass_inspection.v1",
        ("qua kiem tra", "vuot qua kiem tra", "lot qua kiem tra", "danh lua"),
    ),
    AtomRuleSpec(
        "objective",
        "false_content",
        "safety.atom.objective.false_content.v1",
        ("thong tin sai", "noi dung sai", "khong dung su that", "gia"),
    ),
    AtomRuleSpec(
        "objective",
        "unusable",
        "safety.atom.objective.unusable.v1",
        (
            "khong the dung duoc",
            "khong con su dung duoc",
            "khong con gia tri",
            "khong con du lieu",
            "bien mat",
        ),
    ),
    AtomRuleSpec(
        "objective",
        "prevent_recording",
        "safety.atom.objective.prevent_recording.v1",
        (
            "khong ghi lai",
            "ngan ghi lai",
            "khong quay duoc",
            "khong luu lai",
            "ghi lai",
        ),
    ),
    AtomRuleSpec(
        "objective",
        "prevent_discovery",
        "safety.atom.objective.prevent_discovery.v1",
        (
            "khong tim thay",
            "khong tim duoc",
            "kho tim ra",
            "kho truy vet",
            "dieu tra khong tim",
            "bi tim thay",
            "cong an khong tim",
            "khong de cong an tim",
        ),
    ),
    AtomRuleSpec(
        "objective",
        "leave_no_trace",
        "safety.atom.objective.leave_no_trace.v1",
        ("khong de lai dau vet", "xoa dau vet", "mat dau vet"),
    ),
    AtomRuleSpec(
        "objective",
        "avoid_detection",
        "safety.atom.objective.avoid_detection.v1",
        (
            "khong bi phat hien",
            "khong bi bat",
            "khong bi ghi am",
            "khong bi xu ly",
            "tranh bi bat",
        ),
    ),
    AtomRuleSpec(
        "objective",
        "force_payment",
        "safety.atom.objective.force_payment.v1",
        ("tra tien", "tra no", "thanh toan", "giao tai san", "phai tra", "tra"),
    ),
    AtomRuleSpec(
        "objective",
        "frighten_person",
        "safety.atom.objective.frighten_person.v1",
        ("lam ho so", "lam nguoi khac so", "ho so", "so ma"),
    ),
    AtomRuleSpec(
        "objective",
        "delay_investigation",
        "safety.atom.objective.delay_investigation.v1",
        ("keo dai dieu tra", "tri hoan dieu tra", "lam cham dieu tra"),
    ),
    AtomRuleSpec(
        "objective",
        "avoid_appearance",
        "safety.atom.objective.avoid_appearance.v1",
        ("tranh trieu tap", "ne trieu tap", "tranh trinh dien", "khong den lam viec"),
    ),
    AtomRuleSpec(
        "objective",
        "wanted_person",
        "safety.atom.objective.wanted_person.v1",
        ("dang bi truy tim", "dang bi tim kiem", "bi truy na", "bi tim kiem"),
    ),
    AtomRuleSpec(
        "actor",
        "third_party",
        "safety.atom.actor.third_party.v1",
        ("nguoi khac", "nguoi kia", "ai do", "mot nguoi", "ho"),
    ),
    AtomRuleSpec(
        "actor",
        "victim_user",
        "safety.atom.actor.victim_user.v1",
        (
            "toi bi",
            "toi dang bi",
            "cua toi bi",
            "de doa toi",
            "bi de doa",
            "bi uy hiep",
            "ep toi",
            "bi cuong ep",
        ),
    ),
    AtomRuleSpec(
        "actor",
        "user",
        "safety.atom.actor.user.v1",
        ("toi muon", "toi dinh", "giup toi", "chi toi", "de toi", "toi"),
    ),
)

OPERATOR_RULES = (
    OperatorRuleSpec(
        "direct",
        "direct_assistance",
        "safety.intent.direct_assistance.v1",
        (
            "chi toi",
            "chi cach",
            "huong dan toi",
            "huong dan",
            "giup toi",
            "lam sao de",
            "lam sao",
            "lam the nao de",
            "lam the nao",
            "toi muon",
            "toi dinh",
            "van muon",
            "muon",
            "nen lam gi de",
            "hay cho toi",
            "hay",
            "duoc huong dan",
            "co cach nao",
        ),
    ),
    OperatorRuleSpec(
        "method",
        "method_request",
        "safety.intent.method_request.v1",
        ("cach", "phuong phap", "the nao", "bang cach nao", "tung buoc"),
    ),
    OperatorRuleSpec(
        "application",
        "application",
        "safety.intent.application.v1",
        (
            "lam tuong tu",
            "lam theo",
            "ap dung",
            "thuc hien",
            "dung phuong phap",
            "bien thanh cac buoc",
            "chuyen thanh tung buoc",
            "de toi lam",
            "de toi thuc hanh",
            "duoc huong dan",
            "chuyen",
        ),
    ),
    OperatorRuleSpec(
        "concealment",
        "concealment",
        "safety.intent.concealment.v1",
        (
            "khong bi phat hien",
            "khong muon bi phat hien",
            "khong de lai dau vet",
            "khong bi bat",
            "khong bi ghi am",
            "khong bi xu ly",
            "tranh bi bat",
            "khong tim thay",
            "khong tim duoc",
            "kho truy vet",
        ),
    ),
    OperatorRuleSpec(
        "reporting",
        "victim_reporting",
        "safety.context.victim_reporting.v1",
        (
            "bao cong an",
            "muon bao",
            "bao viec",
            "trinh bao",
            "to giac",
            "phan anh",
            "cau cuu",
            "xin tro giup",
            "tim ho tro",
            "lien he co quan chuc nang",
            "bao cho co quan",
            "nen bao ai",
        ),
    ),
    OperatorRuleSpec(
        "prevention",
        "prevention",
        "safety.context.prevention_protection.v1",
        (
            "ngan nguoi khac",
            "ngan chan nguoi khac",
            "khong de nguoi khac",
            "phong ngua",
            "phong tranh hanh vi",
            "phong tranh bi",
        ),
    ),
    OperatorRuleSpec(
        "preservation",
        "preservation",
        "safety.context.prevention_protection.v1",
        (
            "bao ve",
            "bao toan",
            "bao quan",
            "giu nguyen",
            "luu giu",
            "luu lai",
            "khoi phuc",
        ),
    ),
    OperatorRuleSpec(
        "detection",
        "detection",
        "safety.context.prevention_protection.v1",
        ("phat hien", "nhan biet", "kiem tra tinh that", "xac dinh gia mao"),
    ),
    OperatorRuleSpec(
        "compliance",
        "lawful_compliance",
        "safety.context.lawful_compliance.v1",
        (
            "tuan thu",
            "chap hanh",
            "hop tac",
            "chuan bi",
            "phan hoi",
            "xac minh",
            "lien he luat su",
            "trinh dien",
            "den lam viec",
        ),
    ),
    OperatorRuleSpec(
        "description",
        "descriptive_quoted",
        "safety.context.descriptive_quoted.v1",
        (
            "nghia la gi",
            "co vi pham khong",
            "co hop phap khong",
            "bai viet",
            "trong tai lieu",
            "mo ta",
            "phan tich",
            "trich dan",
            "noi ve",
            "toi doc ve",
        ),
    ),
    OperatorRuleSpec(
        "safe_negation",
        "safe_negation",
        "safety.context.safe_negation.v1",
        (
            "khong muon",
            "khong dinh",
            "tranh vo tinh",
            "khong lam mat",
            "khong pha huy",
            "khong xoa",
            "tranh lam mat",
        ),
    ),
    OperatorRuleSpec(
        "police_contact",
        "police_contact",
        "risk.police_contact.v1",
        (
            "nhan",
            "duoc yeu cau",
            "duoc moi",
            "moi lam viec",
            "lien he",
            "goi",
            "gui",
            "thong bao",
            "cong an trieu tap",
            "yeu cau lam viec",
            "yeu cau",
        ),
    ),
)

MATCHED_RULE_IDS = tuple(rule.rule_id for rule in HARM_RULES) + tuple(
    rule.rule_id for rule in RISK_RULES
)
CONCEPT_ATOM_RULE_IDS = tuple(rule.rule_id for rule in ATOM_RULES)
OPERATOR_RULE_IDS = tuple(rule.rule_id for rule in OPERATOR_RULES)


def harm_rule_for_id(rule_id: str) -> HarmRuleSpec | None:
    return next((rule for rule in HARM_RULES if rule.rule_id == rule_id), None)


def harm_rule_for_family(
    family: HarmFamily,
    *,
    property_coercion: bool = False,
) -> HarmRuleSpec:
    wanted = "safety.property_coercion.v1" if property_coercion else None
    for rule in HARM_RULES:
        if rule.family == family and (wanted is None or rule.rule_id == wanted):
            return rule
    raise ValueError("owner harm family is not registered")


def risk_rule_for_id(rule_id: str) -> RiskRuleSpec | None:
    return next((rule for rule in RISK_RULES if rule.rule_id == rule_id), None)


__all__ = [
    "ATOM_RULES",
    "CONCEALMENT_OPERATOR_IDS",
    "CONCEPT_ATOM_RULE_IDS",
    "HARM_RULES",
    "INTENT_OPERATOR_IDS",
    "MATCHED_RULE_IDS",
    "OPERATOR_RULE_IDS",
    "OPERATOR_RULES",
    "POLICE_CONTACT_IDS",
    "RISK_RULES",
    "SAFE_CONTEXT_RULES",
    "SAFETY_REASON_CODES",
    "AtomRuleSpec",
    "HarmFamily",
    "HarmRuleSpec",
    "OperatorRuleSpec",
    "RiskRuleSpec",
    "harm_rule_for_family",
    "harm_rule_for_id",
    "risk_rule_for_id",
]
