"""VietLaw Public Beta V0: curated traffic-law fact contract.

A separate, bounded state model for the traffic vertical -- deliberately NOT
an extension of `contracts/fast_demo.py`'s `FastDemoFacts` (frozen,
deposit-shaped, `extra="forbid"`). Mirrors that module's conventions
(tri-state-like status literals, `extra="forbid"`, conservative defaults)
without importing or modifying it.

Every field defaults to ``"unknown"`` (or ``None`` for the one integer
field): a fact is recorded only when the user's own current message
establishes it, never inferred from vague wording. See
`services/traffic_classifier.py` for the bounded extraction rules.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

VehicleType = Literal["motorcycle", "car", "other", "unknown"]

TrafficViolationType = Literal[
    "red_light",
    "no_helmet",
    "alcohol",
    "speeding",
    "driver_license",
    "phone_use",
    "passenger_limit",
    "vehicle_modification",
    "unknown",
]

LicenseStatus = Literal[
    "forgot",
    "unavailable_at_time",
    "never_licensed",
    "expired",
    "revoked",
    "unknown",
]

ModificationType = Literal[
    "tire",
    "exhaust",
    "frame",
    "lighting",
    "license_plate",
    "other",
    "unknown",
]

# ---------------------------------------------------------------------------
# Traffic Safe Subset V1 (legal-accuracy correction): new bounded facts
# required by the four re-enabled rules. Every one of these defaults to
# `"unknown"` -- never inferred from silence (task §4: "Do not infer `no`
# merely because a condition was not mentioned").
# ---------------------------------------------------------------------------

SignalType = Literal["red", "yellow", "flashing_yellow", "unknown"]

#: A bounded tri-state fact shared by several safe-subset conditions
#: (`traffic_controller_override`, `accident_caused`, `phone_handheld`,
#: `vehicle_in_operation`). `"unknown"` is the ONLY safe default -- it is
#: never coerced to `"no"` just because the user didn't mention it.
TriStateFact = Literal["yes", "no", "unknown"]

HelmetSubject = Literal["driver", "passenger", "unknown"]

HelmetStatus = Literal["not_wearing", "improperly_fastened", "wearing_correctly", "unknown"]

#: Who the detected traffic event is about (Correction Round 1, M-01).
#: Only `"self"` may ever cause a fact to be persisted into per-chat state
#: or a curated answer to be phrased as the user's own confirmed event --
#: see `services/traffic_classifier.py::_detect_attribution` for the
#: bounded structural guards that decide this, and
#: `services/legal_fallback_orchestrator.py` for how each value gates
#: persistence and answer construction.
TrafficAttribution = Literal[
    "self",
    "third_party",
    "hypothetical",
    "educational",
    "negated",
    "unknown",
]

#: The bounded set of topic identifiers the curated pack may cover. Kept here
#: (not only in the data file) so the classifier and the pack agree on the
#: exact vocabulary without importing each other's internals.
TrafficTopicId = Literal[
    "traffic_red_light",
    "traffic_no_helmet",
    "traffic_alcohol",
    "traffic_speeding",
    "traffic_driver_license",
    "traffic_phone_use",
    "traffic_passenger_limit",
    "traffic_vehicle_modification",
]

ALLOWED_TRAFFIC_TOPIC_IDS: frozenset[str] = frozenset(
    {
        "traffic_red_light",
        "traffic_no_helmet",
        "traffic_alcohol",
        "traffic_speeding",
        "traffic_driver_license",
        "traffic_phone_use",
        "traffic_passenger_limit",
        "traffic_vehicle_modification",
    }
)


class TrafficFacts(BaseModel):
    """Per-chat structured traffic facts. `extra="forbid"` so an unrecognized
    field fails loudly at construction rather than silently vanishing."""

    model_config = ConfigDict(extra="forbid")

    vehicle_type: VehicleType = "unknown"
    violation_type: TrafficViolationType = "unknown"
    speed_excess_kmh: int | None = Field(default=None, ge=0)
    alcohol_level: str | None = None
    license_status: LicenseStatus = "unknown"
    passenger_count: int | None = Field(default=None, ge=0)
    modification_type: ModificationType = "unknown"

    # -- Traffic Safe Subset V1 (legal-accuracy correction) -----------------
    #: Red-light Rules A/B: must be exactly `"red"` to match -- `"yellow"`/
    #: `"flashing_yellow"` are excluding values (task §3), `"unknown"` is a
    #: blocking (askable) required fact.
    signal_type: SignalType = "unknown"
    #: Red-light Rules A/B: a NON-blocking excluding condition -- `"yes"`
    #: excludes the rule, `"unknown"`/`"no"` are both safe to proceed on
    #: (task §3: `no_or_not_reported`), never asked about directly.
    traffic_controller_override: TriStateFact = "unknown"
    #: Red-light Rules A/B: same non-blocking excluding-condition shape as
    #: `traffic_controller_override`.
    accident_caused: TriStateFact = "unknown"
    #: Helmet Rule C: must be exactly `"driver"` to match -- `"passenger"`
    #: is an excluding value, `"unknown"` is blocking (askable).
    helmet_subject: HelmetSubject = "unknown"
    #: Helmet Rule C: must be `"not_wearing"` or `"improperly_fastened"` to
    #: match -- `"wearing_correctly"` is an excluding value, `"unknown"` is
    #: blocking (askable).
    helmet_status: HelmetStatus = "unknown"
    #: Phone-use Rule D: must be exactly `"yes"` to match -- `"no"` (hands-
    #: free/mounted) is an excluding value, `"unknown"` is blocking.
    phone_handheld: TriStateFact = "unknown"
    #: Phone-use Rule D: must be exactly `"yes"` to match -- `"no"` (vehicle
    #: stopped) is an excluding value, `"unknown"` is blocking.
    vehicle_in_operation: TriStateFact = "unknown"


#: Bounded operation vocabulary, mirroring `FactUpdateProposal`'s shape.
TrafficFactOperation = Literal["set", "affirm", "negate", "correct"]

#: The only slots a traffic fact update may target. A model or classifier
#: proposing any other slot is rejected outright -- see
#: `services/traffic_classifier.py`.
ALLOWED_TRAFFIC_SLOTS: frozenset[str] = frozenset(
    {
        "vehicle_type",
        "violation_type",
        "speed_excess_kmh",
        "alcohol_level",
        "license_status",
        "passenger_count",
        "modification_type",
        "signal_type",
        "traffic_controller_override",
        "accident_caused",
        "helmet_subject",
        "helmet_status",
        "phone_handheld",
        "vehicle_in_operation",
    }
)


class TrafficFactUpdate(BaseModel):
    """One proposed update to `TrafficFacts`, always re-validated against the
    slot allowlist before it can touch persisted state."""

    model_config = ConfigDict(extra="forbid")

    operation: TrafficFactOperation
    slot: str
    value: str | int | None = None


class ClarificationAnswerKind(str, Enum):
    """Correction Round 2 (M-02-R): the typed result of interpreting a
    message in the context of a SPECIFIC pending traffic clarification
    field -- replaces the Correction Round 1 boolean
    `is_valid_clarification_answer`, whose "any digit counts" rule for
    `speed_excess_kmh`/`alcohol_level`/`passenger_count` let an unrelated
    numeric message ("Hôm nay 30 độ C.") be misread as an answer, retain the
    pending topic on disk, and later contaminate a completely different
    turn. See `services/traffic_classifier.py::parse_clarification_answer`.
    """

    #: The message contains a bounded, field-specific valid value.
    RESOLVED = "resolved"
    #: The user explicitly said they don't know/recall the value.
    UNKNOWN_VALUE = "unknown_value"
    #: The message does not answer the pending field at all -- the pending
    #: clarification must be released, not repeated or silently kept alive.
    UNRELATED = "unrelated"


class ClarificationAnswer(BaseModel):
    """Result of `parse_clarification_answer`. `parsed_value` is only ever
    set when `kind == RESOLVED` (an `int` for the three numeric fields, a
    `str` for the three lexical fields -- mirrors `TrafficFactUpdate.value`'s
    existing `str | int | None` shape)."""

    model_config = ConfigDict(extra="forbid")

    kind: ClarificationAnswerKind
    field: str
    parsed_value: str | int | None = None


# ---------------------------------------------------------------------------
# Traffic Safe Subset V1 (legal-accuracy correction): rule lifecycle and
# selector result types.
# ---------------------------------------------------------------------------

class RuleStatus(str, Enum):
    """A curated traffic rule's lifecycle state. Only `ENABLED` rules may
    ever be looked up or matched -- see
    `services/traffic_source_pack.py::TrafficSourcePack`, which never
    indexes a `DISABLED_PENDING_LEGAL_CORRECTION` row into its searchable
    set at all (not merely a runtime filter -- the row is structurally
    unreachable)."""

    ENABLED = "enabled"
    DISABLED_PENDING_LEGAL_CORRECTION = "disabled_pending_legal_correction"


class RuleSelectionOutcome(str, Enum):
    """The deterministic result of `TrafficSourcePack.select_rule(topic_id,
    facts)` (task §6). `CURATED_VERIFIED` may only ever be emitted for
    `MATCH` -- every other outcome must produce `GENERAL_GUIDANCE` (task
    §7), never a guessed or partial curated answer."""

    #: Every required fact is known and no excluding condition is present.
    MATCH = "match"
    #: A specific single required fact is still unknown -- ask about it
    #: (at most once per topic; the caller enforces that).
    MISSING_FACT = "missing_fact"
    #: No enabled rule exists for this (topic, vehicle_type), OR an
    #: explicit excluding condition was found (e.g. `signal_type="yellow"`,
    #: `helmet_subject="passenger"`, `phone_handheld="no"`).
    NO_SAFE_RULE = "no_safe_rule"
    #: More than one enabled rule matched the same (topic_id, vehicle_type)
    #: key -- a data-integrity safety net, never expected in normal
    #: operation with a de-duplicated pack.
    AMBIGUOUS = "ambiguous"


# ---------------------------------------------------------------------------
# Legal Correction Round 1 (MEDIUM-01): a rule's legal support is a
# structured LIST of provisions, never a single article/clause/point tuple
# plus free prose. A red-light penalty rests on three independently citable
# legal bases (the fine itself, the separate licence-point deduction, and
# the signal-priority rule that makes the conditional wording safe) -- each
# must be individually traceable (its own document/article/clause/URL), not
# merely mentioned inside another citation's `relevance_note` text.
# ---------------------------------------------------------------------------

#: What role a citation plays in supporting the rule's answer. Every
#: enabled rule must carry exactly one `primary_penalty` citation (task §4);
#: `licence_point_deduction` and `signal_interpretation` are additional,
#: topic-dependent (see `traffic_source_pack.py::from_file`'s per-topic
#: citation-shape check).
CitationRole = Literal[
    "primary_penalty",
    "licence_point_deduction",
    "signal_interpretation",
]


class TrafficLegalCitation(BaseModel):
    """One independently traceable legal provision. `point_number` is
    genuinely absent for some citations (e.g. Luật 36/2024/QH15 Điều 11
    khoản 1-4's signal-priority rule spans multiple khoản with no single
    điểm) -- `None` there is an honest absence, not a data-quality gap."""

    model_config = ConfigDict(extra="forbid")

    citation_role: CitationRole
    document_name: str
    document_number: str
    article_number: str
    clause_number: str
    point_number: str | None = None
    official_url: str
    relevance_note: str


__all__ = [
    "ALLOWED_TRAFFIC_SLOTS",
    "ALLOWED_TRAFFIC_TOPIC_IDS",
    "CitationRole",
    "ClarificationAnswer",
    "ClarificationAnswerKind",
    "HelmetStatus",
    "HelmetSubject",
    "LicenseStatus",
    "ModificationType",
    "RuleSelectionOutcome",
    "RuleStatus",
    "SignalType",
    "TrafficAttribution",
    "TrafficFactOperation",
    "TrafficFactUpdate",
    "TrafficFacts",
    "TrafficLegalCitation",
    "TrafficTopicId",
    "TrafficViolationType",
    "TriStateFact",
    "VehicleType",
]
