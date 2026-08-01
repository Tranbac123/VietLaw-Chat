"""VietLaw Public Beta V0: curated traffic rule pack loader and selector.

Mirrors `stores/snippet_store.py::JsonSnippetStore`'s shape (load-at-
construction, validate every row, fail closed) but for the richer per-rule
traffic schema (task §5.2 of the original Public Beta V0 task).

Traffic Safe Subset V1 (legal-accuracy correction) rewrote the selection
model after an independent legal review
(`VIETLAW_PUBLIC_BETA_V0_TRAFFIC_LEGAL_ACCURACY_REVIEW_V1.md`) found that
the runtime never used a rule's structured facts beyond "topic_id +
vehicle_type" to pick an answer -- a message that partially matched a rule
(e.g. a red-light question where the light might have been yellow, or a
helmet question about a passenger rather than the driver) received the same
`CURATED_VERIFIED` excerpt as a fully-matching one. `TrafficRuleRecord` now
carries `status` (only `enabled` rows are ever indexed at all -- a disabled
row is structurally unreachable, not merely runtime-filtered),
`required_facts` (fields that must be explicitly known to match), and
`excluded_facts` ((field, value) pairs that disqualify the rule outright
when the CURRENT fact equals that value). `select_rule()` is the single
place this logic lives; the orchestrator never inspects a rule's facts
directly.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from ..contracts.traffic import (
    ALLOWED_TRAFFIC_TOPIC_IDS,
    RuleSelectionOutcome,
    RuleStatus,
    TrafficFacts,
    TrafficLegalCitation,
    VehicleType,
)

#: Per-topic EXACT citation-role shape (Legal Correction Round 2, MEDIUM-01
#: of `VIETLAW_TRAFFIC_SAFE_SUBSET_V1_LEGAL_CORRECTION_ROUND_1_VERIFICATION_
#: V1.md`): a role name -> the exact count an ENABLED rule of that topic
#: must carry, and NO OTHER role at all. A topic not listed here has no
#: shape requirement beyond the generic "non-empty, exactly one
#: primary_penalty" check.
#:
#: Round 1's version of this dict only checked the counts of the roles it
#: explicitly listed (`traffic_no_helmet` never mentioned
#: `signal_interpretation`), so an enabled helmet row carrying an EXTRA
#: `signal_interpretation` citation -- one that doesn't belong to that
#: rule's legal basis at all -- passed validation silently. A role simply
#: absent from a topic's shape here means "zero of this role, no
#: exceptions" (an implicit zero, matched by `Counter` equality against the
#: citations' own role multiset -- never a minimum-count check).
_EXACT_CITATION_SHAPE_BY_TOPIC: dict[str, dict[str, int]] = {
    "traffic_red_light": {
        "primary_penalty": 1,
        "licence_point_deduction": 1,
        "signal_interpretation": 1,
    },
    "traffic_no_helmet": {
        "primary_penalty": 1,
    },
}

#: Citation roles whose legal locator always includes a specific điểm --
#: `signal_interpretation` (Luật 36/2024/QH15 Điều 11 khoản 1-4) is the one
#: documented exception (task §4: `point=null`), so it is excluded here.
_ROLES_REQUIRING_POINT: frozenset[str] = frozenset({"primary_penalty", "licence_point_deduction"})


class TrafficRuleRecord(BaseModel):
    """One curated, officially-sourced traffic rule entry (task §5.2 of the
    original Public Beta V0 task; extended by the Traffic Safe Subset V1
    correction with `rule_id`, `status`, `required_facts`/`excluded_facts`
    used by the selector, `point_number`, `penalty_min_vnd`/
    `penalty_max_vnd`/`licence_points_deducted` (structured penalty data,
    not just prose), `answer_template` (the conditional-wording final
    answer text), and `uncertainty_conditions` (non-blocking excluded-fact
    names surfaced in the answer as "nếu không thuộc trường hợp...")."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    status: RuleStatus = RuleStatus.DISABLED_PENDING_LEGAL_CORRECTION
    topic_id: str
    vehicle_type: VehicleType
    required_facts: list[str] = Field(default_factory=list)
    #: `[[field_name, disqualifying_value], ...]` -- JSON-friendly (a tuple
    #: is not valid JSON); validated pairwise in `select_rule`.
    excluded_facts: list[list[str]] = Field(default_factory=list)
    legal_document_name: str
    legal_document_number: str
    article_number: str | None = None
    clause_number: str | None = None
    point_number: str | None = None
    effective_date: str
    official_url: str
    source_title: str
    source_excerpt: str
    answer_constraints: list[str] = Field(default_factory=list)
    #: Field name -> the ONE clarification question for that field. Replaces
    #: the single `clarification_question` string from the original Public
    #: Beta V0 schema now that a rule may have more than one askable
    #: required fact beyond `vehicle_type` (e.g. Rule C: `helmet_subject`
    #: AND `helmet_status`).
    clarification_questions: dict[str, str] = Field(default_factory=dict)
    last_verified_at: str
    penalty_min_vnd: int | None = None
    penalty_max_vnd: int | None = None
    licence_points_deducted: int | None = None
    #: The final, conditionally-worded answer text (e.g. "Nếu... không
    #: thuộc trường hợp... mức phạt là..."). Preferred over `source_excerpt`
    #: for the rendered summary when present -- see
    #: `legal_fallback_orchestrator.py::_build_curated_traffic_response`.
    answer_template: str | None = None
    #: Names of the non-blocking excluded facts this rule's `answer_template`
    #: already phrases conditionally (task §4: "use conditional wording when
    #: a non-blocking fact is not reported").
    uncertainty_conditions: list[str] = Field(default_factory=list)
    #: Human-readable audit trail for a `disabled_pending_legal_correction`
    #: row (e.g. "HIGH-01: missing licence-point deduction..."). Never
    #: rendered to a user; purely for repository/report transparency.
    disabled_reason: str | None = None
    #: Legal Correction Round 1 (MEDIUM-01): the structured, independently
    #: traceable list of legal provisions supporting this rule's answer --
    #: the SOURCE OF TRUTH for `_build_curated_traffic_response`'s rendered
    #: sources (one `SourceObject` per entry). `source_excerpt`/
    #: `article_number`/`clause_number`/`point_number` above are kept only
    #: for backward compatibility (the top-level fields mirror the
    #: `primary_penalty` citation) and internal legacy validation -- they are
    #: never the source of truth for a response once `legal_citations` is
    #: populated. Validated non-empty, with exactly one `primary_penalty`
    #: and a topic-appropriate shape, for every ENABLED row (see
    #: `_validate_legal_citations` below).
    legal_citations: list[TrafficLegalCitation] = Field(default_factory=list)


class TrafficRuleSelection(BaseModel):
    """Result of `TrafficSourcePack.select_rule()` (task §6)."""

    model_config = ConfigDict(extra="forbid")

    outcome: RuleSelectionOutcome
    rule: TrafficRuleRecord | None = None
    missing_field: str | None = None


class TrafficSourcePackError(RuntimeError):
    pass


def _validate_legal_citations(record: "TrafficRuleRecord") -> None:
    """Legal Correction Round 1 (task §7): structural checks on an ENABLED
    row's `legal_citations`, run at load time so a malformed enabled rule
    fails startup rather than silently under-citing a curated answer.
    Never applied to a disabled row -- it "may retain incomplete historical
    data because [it] remain[s] structurally unreachable" (task §7)."""

    citations = record.legal_citations
    if not citations:
        raise TrafficSourcePackError(f"enabled rule {record.rule_id} has no legal_citations")

    seen_locations: set[tuple[str, str, str, str | None]] = set()
    role_counts: dict[str, int] = {}
    for citation in citations:
        if not citation.official_url:
            raise TrafficSourcePackError(
                f"enabled rule {record.rule_id}: citation {citation.citation_role!r} has no official_url"
            )
        if not citation.document_number:
            raise TrafficSourcePackError(
                f"enabled rule {record.rule_id}: citation {citation.citation_role!r} has no document_number"
            )
        if not (citation.article_number and citation.clause_number):
            raise TrafficSourcePackError(
                f"enabled rule {record.rule_id}: citation {citation.citation_role!r} "
                f"is missing article/clause metadata"
            )
        if citation.citation_role in _ROLES_REQUIRING_POINT and not citation.point_number:
            raise TrafficSourcePackError(
                f"enabled rule {record.rule_id}: citation {citation.citation_role!r} "
                f"requires a point_number"
            )
        location = (citation.citation_role, citation.article_number, citation.clause_number, citation.point_number)
        if location in seen_locations:
            raise TrafficSourcePackError(
                f"enabled rule {record.rule_id}: duplicate citation role+location {location}"
            )
        seen_locations.add(location)
        role_counts[citation.citation_role] = role_counts.get(citation.citation_role, 0) + 1

    if role_counts.get("primary_penalty", 0) != 1:
        raise TrafficSourcePackError(
            f"enabled rule {record.rule_id} must have exactly one primary_penalty citation, "
            f"found {role_counts.get('primary_penalty', 0)}"
        )

    # Legal Correction Round 2 (MEDIUM-01): the accepted role multiset must
    # be EXACTLY equal to the configured shape -- not merely satisfy a
    # per-role minimum. `Counter` equality catches every failure mode in
    # one comparison: a missing required role, an extra role the shape
    # never mentions at all (the exact defect Round 1 missed for
    # `traffic_no_helmet` + an unexpected `signal_interpretation`), a
    # duplicate beyond the expected count, and a wrong count for any role.
    # Neither Counter here ever holds an explicit zero entry, so this does
    # not depend on Python's per-version Counter-with-zero-counts equality
    # semantics -- "absent from the shape" and "absent from the citations"
    # are both simply missing keys.
    expected_shape = _EXACT_CITATION_SHAPE_BY_TOPIC.get(record.topic_id)
    if expected_shape is not None:
        actual_counts = Counter(role_counts)
        expected_counts = Counter(expected_shape)
        if actual_counts != expected_counts:
            raise TrafficSourcePackError(
                f"enabled rule {record.rule_id} (topic {record.topic_id}) has citation role "
                f"shape {dict(actual_counts)}, expected exactly {dict(expected_counts)}"
            )
        if sum(actual_counts.values()) != sum(expected_counts.values()):
            # Unreachable given the equality check above (defense in depth,
            # per task §1: "verify the total citation count equals the sum
            # of expected counts").
            raise TrafficSourcePackError(
                f"enabled rule {record.rule_id} (topic {record.topic_id}) citation count "
                f"does not match the expected shape total"
            )


class TrafficSourcePack:
    """Loaded, validated curated traffic rules. Only `status == ENABLED`
    rows are ever indexed for lookup/selection -- a disabled row cannot be
    returned by `find()` or matched by `select_rule()` under any
    circumstance (task §2: "The source-pack loader must never return a
    disabled rule"), not merely suppressed by a runtime trust check."""

    def __init__(self, rules: list[TrafficRuleRecord]) -> None:
        self._all_rules = rules
        self._enabled_rules = [r for r in rules if r.status == RuleStatus.ENABLED]
        self._by_key: dict[tuple[str, str], TrafficRuleRecord] = {}
        for rule in self._enabled_rules:
            self._by_key[(rule.topic_id, rule.vehicle_type)] = rule

    @classmethod
    def from_file(cls, path: Path) -> "TrafficSourcePack":
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TrafficSourcePackError(f"cannot read traffic pack: {exc}") from exc

        rules_raw = raw.get("rules") if isinstance(raw, dict) else None
        if not isinstance(rules_raw, list):
            raise TrafficSourcePackError("traffic pack missing 'rules' list")

        rules: list[TrafficRuleRecord] = []
        seen_rule_ids: set[str] = set()
        seen_enabled_keys: set[tuple[str, str]] = set()
        for entry in rules_raw:
            try:
                record = TrafficRuleRecord.model_validate(entry)
            except Exception as exc:  # noqa: BLE001 - one bad row must not crash startup
                raise TrafficSourcePackError(f"invalid traffic rule entry: {exc}") from exc
            if record.topic_id not in ALLOWED_TRAFFIC_TOPIC_IDS:
                raise TrafficSourcePackError(f"unrecognized topic_id: {record.topic_id}")
            if record.rule_id in seen_rule_ids:
                raise TrafficSourcePackError(f"duplicate rule_id: {record.rule_id}")
            seen_rule_ids.add(record.rule_id)
            if record.status == RuleStatus.ENABLED:
                key = (record.topic_id, record.vehicle_type)
                if key in seen_enabled_keys:
                    raise TrafficSourcePackError(
                        f"duplicate enabled (topic_id, vehicle_type) selector: {key}"
                    )
                seen_enabled_keys.add(key)
                # Task §7: CURATED_VERIFIED requires a primary official URL
                # and article/clause/point metadata on every enabled rule --
                # enforced here, at load time, not just hoped for.
                if not record.official_url:
                    raise TrafficSourcePackError(f"enabled rule {record.rule_id} has no official_url")
                if not (record.article_number and record.clause_number and record.point_number):
                    raise TrafficSourcePackError(
                        f"enabled rule {record.rule_id} is missing article/clause/point metadata"
                    )
                _validate_legal_citations(record)
            rules.append(record)
        return cls(rules)

    @property
    def topic_ids(self) -> frozenset[str]:
        """Topic IDs with at least one ENABLED rule. A topic with only
        disabled rows (e.g. `traffic_alcohol`) does not appear here."""

        return frozenset(rule.topic_id for rule in self._enabled_rules)

    @property
    def enabled_rule_ids(self) -> frozenset[str]:
        return frozenset(rule.rule_id for rule in self._enabled_rules)

    @property
    def total_rule_count(self) -> int:
        """Deployment Correction Round 2 (MEDIUM-01): total row count
        (enabled + disabled), for the exact-traffic-inventory health
        invariant. Read-only introspection -- never used by `select_rule`
        or any selection/citation logic."""

        return len(self._all_rules)

    @property
    def disabled_rule_count(self) -> int:
        """Deployment Correction Round 2 (MEDIUM-01): row count with
        `status != ENABLED`, for the exact-traffic-inventory health
        invariant."""

        return len(self._all_rules) - len(self._enabled_rules)

    @property
    def disabled_topic_ids(self) -> frozenset[str]:
        """Topic IDs that have rows in the pack but none of them enabled."""

        all_topics = frozenset(rule.topic_id for rule in self._all_rules)
        return all_topics - self.topic_ids

    def find(self, topic_id: str, vehicle_type: str) -> TrafficRuleRecord | None:
        """Exact (topic, vehicle_type) lookup among ENABLED rules only.
        Fails closed (`None`) rather than guessing a nearby vehicle type,
        falling back to a disabled row, or defaulting to any row at all."""

        return self._by_key.get((topic_id, vehicle_type))

    def select_rule(self, topic_id: str, facts: TrafficFacts) -> TrafficRuleSelection:
        """Task §6: the single place rule selection happens. Never returns
        `MATCH` for a disabled rule (structurally impossible -- disabled
        rows are not in `self._by_key`), an incomplete rule (missing
        required facts), or an excluded one (an explicit disqualifying
        fact value is present)."""

        candidates = [r for r in self._enabled_rules if r.topic_id == topic_id]
        if not candidates:
            return TrafficRuleSelection(outcome=RuleSelectionOutcome.NO_SAFE_RULE)

        vehicle_type = facts.vehicle_type
        if vehicle_type == "unknown":
            return TrafficRuleSelection(outcome=RuleSelectionOutcome.MISSING_FACT, missing_field="vehicle_type")

        matching = [r for r in candidates if r.vehicle_type == vehicle_type]
        if not matching:
            # e.g. car helmet/phone-use, or a vehicle_type this topic simply
            # has no enabled rule for -- fail closed, never borrow a nearby
            # vehicle's rule.
            return TrafficRuleSelection(outcome=RuleSelectionOutcome.NO_SAFE_RULE)
        if len(matching) > 1:
            # Data-integrity safety net: `from_file` already rejects a
            # duplicate enabled (topic_id, vehicle_type) key, so this should
            # be unreachable in practice; kept as defense in depth for a
            # pack constructed directly (bypassing `from_file`), e.g. tests.
            return TrafficRuleSelection(outcome=RuleSelectionOutcome.AMBIGUOUS)
        rule = matching[0]

        for pair in rule.excluded_facts:
            field_name, disqualifying_value = pair[0], pair[1]
            if getattr(facts, field_name, None) == disqualifying_value:
                return TrafficRuleSelection(outcome=RuleSelectionOutcome.NO_SAFE_RULE, rule=rule)

        for field_name in rule.required_facts:
            value = getattr(facts, field_name, None)
            if value in (None, "unknown"):
                return TrafficRuleSelection(
                    outcome=RuleSelectionOutcome.MISSING_FACT, rule=rule, missing_field=field_name
                )

        return TrafficRuleSelection(outcome=RuleSelectionOutcome.MATCH, rule=rule)


__all__ = [
    "TrafficRuleRecord",
    "TrafficRuleSelection",
    "TrafficSourcePack",
    "TrafficSourcePackError",
]
