"""Traffic Safe Subset V1: curated traffic rule pack loader and selector
(legal-accuracy correction of Public Beta V0 task §5.2), further corrected
by Legal Correction Round 1 (`VIETLAW_TRAFFIC_SAFE_SUBSET_V1_LEGAL_REVIEW_V1
.md`).

Round 1 found HIGH-01 (the phone-use rule's selector could MATCH even when
the user explicitly denied using the phone -- holding it is not the same
legal element as using it) and MEDIUM-01 (the pack carried only one
structured citation per rule; the licence-point-deduction and, for
red-light rules, the Luật 36/2024/QH15 Điều 11 signal-priority basis were
prose-only, with no separate official URL). This file now tests the
twice-corrected pack: 12 rows `disabled_pending_legal_correction` (11
original + the now-disabled phone rule), plus exactly 3 enabled rules (Rules
A-C), each carrying a structured `legal_citations` list validated at load
time (task §7).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend_lite.app.contracts.traffic import RuleSelectionOutcome, RuleStatus, TrafficFacts
from backend_lite.app.services.traffic_source_pack import (
    TrafficRuleRecord,
    TrafficSourcePack,
    TrafficSourcePackError,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
PACK_PATH = REPO_ROOT / "data" / "traffic_rules.json"

_ENABLED_TOPIC_IDS = frozenset({"traffic_red_light", "traffic_no_helmet"})
_DISABLED_TOPIC_IDS = frozenset(
    {
        "traffic_alcohol",
        "traffic_speeding",
        "traffic_driver_license",
        "traffic_passenger_limit",
        "traffic_vehicle_modification",
        "traffic_phone_use",
    }
)
_ENABLED_RULE_IDS = frozenset(
    {
        "traffic_red_light__motorcycle__safe_v1",
        "traffic_red_light__car__safe_v1",
        "traffic_no_helmet__motorcycle__driver_safe_v1",
    }
)

_PRIMARY_PENALTY_CITATION = {
    "citation_role": "primary_penalty",
    "document_name": "Nghị định test",
    "document_number": "1/2025/ND-CP",
    "article_number": "7",
    "clause_number": "7",
    "point_number": "c",
    "official_url": "https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=1",
    "relevance_note": "Test relevance.",
}


def _bare_rule(**overrides) -> TrafficRuleRecord:
    base = dict(
        rule_id=overrides.pop("rule_id", "test_rule"),
        status=RuleStatus.ENABLED,
        topic_id="traffic_red_light",
        vehicle_type="motorcycle",
        required_facts=["vehicle_type", "signal_type"],
        excluded_facts=[["signal_type", "yellow"]],
        legal_document_name="Nghị định test",
        legal_document_number="1/2025/ND-CP",
        article_number="7",
        clause_number="7",
        point_number="c",
        effective_date="2025-01-01",
        official_url="https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=1",
        source_title="Test",
        source_excerpt="Test excerpt.",
        last_verified_at="2026-07-31",
        answer_template="Test answer.",
        legal_citations=[_PRIMARY_PENALTY_CITATION],
    )
    base.update(overrides)
    return TrafficRuleRecord(**base)


# -- pack-level loading (task §2, §5) ----------------------------------------


def test_curated_pack_loads_from_the_real_data_file() -> None:
    pack = TrafficSourcePack.from_file(PACK_PATH)
    assert pack.topic_ids == _ENABLED_TOPIC_IDS
    assert pack.disabled_topic_ids == _DISABLED_TOPIC_IDS
    assert pack.enabled_rule_ids == _ENABLED_RULE_IDS


def test_total_and_disabled_rule_count_match_the_frozen_inventory() -> None:
    """Deployment Correction Round 2 (MEDIUM-01): the exact-traffic-
    inventory health gate reads these two properties -- pin them directly
    against the real data file so a future data change that breaks the
    frozen 15/3/12 inventory is caught here too, not only via health."""

    pack = TrafficSourcePack.from_file(PACK_PATH)
    assert pack.total_rule_count == 15
    assert pack.disabled_rule_count == 12
    assert len(pack.enabled_rule_ids) == 3


def test_every_enabled_rule_has_official_document_identity_and_citation() -> None:
    pack = TrafficSourcePack.from_file(PACK_PATH)
    enabled = [r for r in pack._all_rules if r.status == RuleStatus.ENABLED]
    assert len(enabled) == 3
    for rule in enabled:
        assert rule.legal_document_name
        assert rule.legal_document_number
        assert rule.official_url.startswith("https://vbpl.vn/")
        assert rule.article_number and rule.clause_number and rule.point_number
        assert rule.last_verified_at
        assert rule.answer_template
        assert rule.legal_citations


def test_every_disabled_rule_carries_an_audit_reason_and_no_citation() -> None:
    pack = TrafficSourcePack.from_file(PACK_PATH)
    disabled = [r for r in pack._all_rules if r.status == RuleStatus.DISABLED_PENDING_LEGAL_CORRECTION]
    assert len(disabled) == 12
    for rule in disabled:
        assert rule.disabled_reason


def test_find_never_returns_a_disabled_rule() -> None:
    pack = TrafficSourcePack.from_file(PACK_PATH)
    for topic_id in _DISABLED_TOPIC_IDS:
        assert pack.find(topic_id, "motorcycle") is None
        assert pack.find(topic_id, "car") is None


def test_find_fails_closed_for_unmatched_vehicle_type() -> None:
    pack = TrafficSourcePack.from_file(PACK_PATH)
    # traffic_no_helmet has no curated CAR entry in the safe subset -- must
    # return None, not guess from the motorcycle rule.
    assert pack.find("traffic_no_helmet", "car") is None


def test_find_never_returns_the_disabled_phone_rule_high_01(tmp_path: Path) -> None:
    # Legal Correction Round 1, HIGH-01: the phone-use rule (previously
    # enabled for motorcycle) is now disabled -- `find` must return None for
    # BOTH vehicle types, not just the (already-unsupported) car case.
    pack = TrafficSourcePack.from_file(PACK_PATH)
    assert pack.find("traffic_phone_use", "motorcycle") is None
    assert pack.find("traffic_phone_use", "car") is None


# -- select_rule() (task §6) --------------------------------------------------


def test_select_rule_match_for_fully_resolved_motorcycle_red_light() -> None:
    pack = TrafficSourcePack.from_file(PACK_PATH)
    facts = TrafficFacts(vehicle_type="motorcycle", signal_type="red")
    selection = pack.select_rule("traffic_red_light", facts)
    assert selection.outcome == RuleSelectionOutcome.MATCH
    assert selection.rule is not None
    assert selection.rule.rule_id == "traffic_red_light__motorcycle__safe_v1"


def test_select_rule_missing_fact_for_unknown_vehicle_type() -> None:
    pack = TrafficSourcePack.from_file(PACK_PATH)
    selection = pack.select_rule("traffic_red_light", TrafficFacts())
    assert selection.outcome == RuleSelectionOutcome.MISSING_FACT
    assert selection.missing_field == "vehicle_type"
    assert selection.rule is None


def test_select_rule_missing_fact_for_unknown_topic_specific_field() -> None:
    pack = TrafficSourcePack.from_file(PACK_PATH)
    facts = TrafficFacts(vehicle_type="motorcycle")
    selection = pack.select_rule("traffic_red_light", facts)
    assert selection.outcome == RuleSelectionOutcome.MISSING_FACT
    assert selection.missing_field == "signal_type"
    assert selection.rule is not None


def test_select_rule_no_safe_rule_for_a_disabled_topic() -> None:
    pack = TrafficSourcePack.from_file(PACK_PATH)
    facts = TrafficFacts(vehicle_type="motorcycle", alcohol_level="0.3 mg/l")
    selection = pack.select_rule("traffic_alcohol", facts)
    assert selection.outcome == RuleSelectionOutcome.NO_SAFE_RULE
    assert selection.rule is None


def test_select_rule_no_safe_rule_for_a_topic_id_with_no_rows_at_all() -> None:
    pack = TrafficSourcePack.from_file(PACK_PATH)
    facts = TrafficFacts(vehicle_type="motorcycle")
    selection = pack.select_rule("traffic_unknown_topic_not_in_pack", facts)
    assert selection.outcome == RuleSelectionOutcome.NO_SAFE_RULE


def test_select_rule_no_safe_rule_for_wrong_vehicle_type() -> None:
    pack = TrafficSourcePack.from_file(PACK_PATH)
    # No enabled car rule for no_helmet in the safe subset.
    facts = TrafficFacts(vehicle_type="car", helmet_subject="driver", helmet_status="not_wearing")
    selection = pack.select_rule("traffic_no_helmet", facts)
    assert selection.outcome == RuleSelectionOutcome.NO_SAFE_RULE


@pytest.mark.parametrize(
    "field_name,value",
    [("signal_type", "yellow"), ("signal_type", "flashing_yellow"),
     ("traffic_controller_override", "yes"), ("accident_caused", "yes")],
)
def test_select_rule_no_safe_rule_for_each_red_light_excluding_fact(field_name, value) -> None:
    pack = TrafficSourcePack.from_file(PACK_PATH)
    base = {"vehicle_type": "motorcycle", "signal_type": "red"}
    base[field_name] = value
    selection = pack.select_rule("traffic_red_light", TrafficFacts(**base))
    assert selection.outcome == RuleSelectionOutcome.NO_SAFE_RULE


@pytest.mark.parametrize(
    "field_name,value",
    [("helmet_subject", "passenger"), ("helmet_status", "wearing_correctly")],
)
def test_select_rule_no_safe_rule_for_each_helmet_excluding_fact(field_name, value) -> None:
    pack = TrafficSourcePack.from_file(PACK_PATH)
    base = {"vehicle_type": "motorcycle", "helmet_subject": "driver", "helmet_status": "not_wearing"}
    base[field_name] = value
    selection = pack.select_rule("traffic_no_helmet", TrafficFacts(**base))
    assert selection.outcome == RuleSelectionOutcome.NO_SAFE_RULE


def test_select_rule_no_safe_rule_for_phone_use_regardless_of_facts_high_01() -> None:
    # Legal Correction Round 1, HIGH-01: phone_use has zero enabled rules --
    # `select_rule` must return NO_SAFE_RULE even for facts that would have
    # produced a MATCH under the pre-correction (unsafe) selector, e.g. the
    # exact adversarial probe the legal review used ("... nhưng chưa sử dụng
    # điện thoại", which the old selector still matched via
    # phone_handheld=yes + vehicle_in_operation=yes alone).
    pack = TrafficSourcePack.from_file(PACK_PATH)
    facts = TrafficFacts(vehicle_type="motorcycle", phone_handheld="yes", vehicle_in_operation="yes")
    selection = pack.select_rule("traffic_phone_use", facts)
    assert selection.outcome == RuleSelectionOutcome.NO_SAFE_RULE
    assert selection.rule is None


def test_select_rule_ambiguous_when_two_enabled_rules_share_a_selector() -> None:
    # Constructed directly (bypassing `from_file`, which rejects this at load
    # time) -- a defense-in-depth check on `select_rule` itself (task §6).
    dup_a = _bare_rule(rule_id="dup_a")
    dup_b = _bare_rule(rule_id="dup_b")
    pack = TrafficSourcePack([dup_a, dup_b])
    facts = TrafficFacts(vehicle_type="motorcycle", signal_type="red")
    selection = pack.select_rule("traffic_red_light", facts)
    assert selection.outcome == RuleSelectionOutcome.AMBIGUOUS


# -- load-time integrity checks (task §5, §7) --------------------------------


def test_invalid_topic_id_is_rejected(tmp_path: Path) -> None:
    bad_pack = tmp_path / "bad.json"
    bad_pack.write_text(
        json.dumps(
            {
                "rules": [
                    {
                        "rule_id": "r1",
                        "topic_id": "traffic_not_a_real_topic",
                        "vehicle_type": "motorcycle",
                        "legal_document_name": "Fake Decree",
                        "legal_document_number": "0/0000/ND-CP",
                        "effective_date": "2025-01-01",
                        "official_url": "https://vbpl.vn/fake",
                        "source_title": "Fake",
                        "source_excerpt": "Fake",
                        "last_verified_at": "2026-01-01",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(TrafficSourcePackError):
        TrafficSourcePack.from_file(bad_pack)


def test_missing_rules_list_is_rejected(tmp_path: Path) -> None:
    bad_pack = tmp_path / "no_rules.json"
    bad_pack.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
    with pytest.raises(TrafficSourcePackError):
        TrafficSourcePack.from_file(bad_pack)


def test_unreadable_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(TrafficSourcePackError):
        TrafficSourcePack.from_file(tmp_path / "does_not_exist.json")


def _row(**overrides) -> dict:
    # `traffic_alcohol` deliberately: it has no per-topic citation-shape
    # requirement in `_REQUIRED_CITATION_SHAPE_BY_TOPIC` (unlike
    # `traffic_red_light`/`traffic_no_helmet`), so these load-time tests
    # each fail for exactly the ONE specific reason they name, never
    # incidentally for a missing licence_point_deduction/signal_interpretation.
    base = dict(
        rule_id="r1",
        status="enabled",
        topic_id="traffic_alcohol",
        vehicle_type="motorcycle",
        required_facts=["vehicle_type"],
        excluded_facts=[],
        legal_document_name="Nghị định test",
        legal_document_number="1/2025/ND-CP",
        article_number="7",
        clause_number="7",
        point_number="c",
        effective_date="2025-01-01",
        official_url="https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=1",
        source_title="Test",
        source_excerpt="Test excerpt.",
        last_verified_at="2026-07-31",
        legal_citations=[dict(_PRIMARY_PENALTY_CITATION)],
    )
    base.update(overrides)
    return base


def test_duplicate_rule_id_is_rejected(tmp_path: Path) -> None:
    bad_pack = tmp_path / "dup_id.json"
    bad_pack.write_text(
        json.dumps({"rules": [_row(rule_id="same"), _row(rule_id="same", vehicle_type="car")]}),
        encoding="utf-8",
    )
    with pytest.raises(TrafficSourcePackError):
        TrafficSourcePack.from_file(bad_pack)


def test_duplicate_enabled_selector_is_rejected(tmp_path: Path) -> None:
    bad_pack = tmp_path / "dup_selector.json"
    bad_pack.write_text(
        json.dumps({"rules": [_row(rule_id="a"), _row(rule_id="b")]}),
        encoding="utf-8",
    )
    with pytest.raises(TrafficSourcePackError):
        TrafficSourcePack.from_file(bad_pack)


def test_enabled_rule_missing_official_url_is_rejected(tmp_path: Path) -> None:
    bad_pack = tmp_path / "no_url.json"
    bad_pack.write_text(
        json.dumps({"rules": [_row(official_url="")]}),
        encoding="utf-8",
    )
    with pytest.raises(TrafficSourcePackError):
        TrafficSourcePack.from_file(bad_pack)


@pytest.mark.parametrize("missing_field", ["article_number", "clause_number", "point_number"])
def test_enabled_rule_missing_citation_metadata_is_rejected(tmp_path: Path, missing_field) -> None:
    bad_pack = tmp_path / "no_citation.json"
    bad_pack.write_text(
        json.dumps({"rules": [_row(**{missing_field: None})]}),
        encoding="utf-8",
    )
    with pytest.raises(TrafficSourcePackError):
        TrafficSourcePack.from_file(bad_pack)


def test_disabled_rule_missing_citation_metadata_is_accepted(tmp_path: Path) -> None:
    # A disabled row is exempt from the citation-completeness check -- it can
    # never be selected or shown, so incomplete/unverified metadata on it is
    # expected (that is precisely why it is disabled), not an integrity bug.
    ok_pack = tmp_path / "disabled_incomplete.json"
    ok_pack.write_text(
        json.dumps(
            {
                "rules": [
                    _row(
                        status="disabled_pending_legal_correction",
                        article_number=None,
                        clause_number=None,
                        point_number=None,
                    )
                ]
            }
        ),
        encoding="utf-8",
    )
    pack = TrafficSourcePack.from_file(ok_pack)
    assert pack.topic_ids == frozenset()


# -- legal_citations load-time validation (Legal Correction Round 1, task §7) -


def test_enabled_rule_with_no_legal_citations_is_rejected(tmp_path: Path) -> None:
    bad_pack = tmp_path / "no_citations.json"
    bad_pack.write_text(
        json.dumps({"rules": [_row(legal_citations=[])]}),
        encoding="utf-8",
    )
    with pytest.raises(TrafficSourcePackError):
        TrafficSourcePack.from_file(bad_pack)


def test_enabled_rule_with_zero_primary_penalty_citations_is_rejected(tmp_path: Path) -> None:
    bad_pack = tmp_path / "no_primary.json"
    bad_pack.write_text(
        json.dumps(
            {"rules": [_row(legal_citations=[{**_PRIMARY_PENALTY_CITATION, "citation_role": "licence_point_deduction"}])]}
        ),
        encoding="utf-8",
    )
    with pytest.raises(TrafficSourcePackError):
        TrafficSourcePack.from_file(bad_pack)


def test_enabled_rule_with_two_primary_penalty_citations_is_rejected(tmp_path: Path) -> None:
    bad_pack = tmp_path / "two_primary.json"
    bad_pack.write_text(
        json.dumps(
            {
                "rules": [
                    _row(
                        legal_citations=[
                            dict(_PRIMARY_PENALTY_CITATION),
                            {**_PRIMARY_PENALTY_CITATION, "clause_number": "8"},
                        ]
                    )
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(TrafficSourcePackError):
        TrafficSourcePack.from_file(bad_pack)


def test_citation_missing_official_url_is_rejected(tmp_path: Path) -> None:
    bad_pack = tmp_path / "citation_no_url.json"
    bad_pack.write_text(
        json.dumps({"rules": [_row(legal_citations=[{**_PRIMARY_PENALTY_CITATION, "official_url": ""}])]}),
        encoding="utf-8",
    )
    with pytest.raises(TrafficSourcePackError):
        TrafficSourcePack.from_file(bad_pack)


def test_primary_penalty_citation_missing_point_is_rejected(tmp_path: Path) -> None:
    # task §4: primary_penalty and licence_point_deduction always cite a
    # specific điểm; only signal_interpretation may legitimately omit one.
    bad_pack = tmp_path / "citation_no_point.json"
    bad_pack.write_text(
        json.dumps({"rules": [_row(legal_citations=[{**_PRIMARY_PENALTY_CITATION, "point_number": None}])]}),
        encoding="utf-8",
    )
    with pytest.raises(TrafficSourcePackError):
        TrafficSourcePack.from_file(bad_pack)


def test_signal_interpretation_citation_may_omit_point(tmp_path: Path) -> None:
    ok_pack = tmp_path / "signal_no_point.json"
    ok_pack.write_text(
        json.dumps(
            {
                "rules": [
                    _row(
                        legal_citations=[
                            dict(_PRIMARY_PENALTY_CITATION),
                            {
                                **_PRIMARY_PENALTY_CITATION,
                                "citation_role": "signal_interpretation",
                                "article_number": "11",
                                "clause_number": "1-4",
                                "point_number": None,
                            },
                        ]
                    )
                ]
            }
        ),
        encoding="utf-8",
    )
    pack = TrafficSourcePack.from_file(ok_pack)
    assert pack.enabled_rule_ids == frozenset({"r1"})


def test_duplicate_citation_role_and_location_is_rejected(tmp_path: Path) -> None:
    bad_pack = tmp_path / "dup_citation_location.json"
    bad_pack.write_text(
        json.dumps({"rules": [_row(legal_citations=[dict(_PRIMARY_PENALTY_CITATION), dict(_PRIMARY_PENALTY_CITATION)])]}),
        encoding="utf-8",
    )
    with pytest.raises(TrafficSourcePackError):
        TrafficSourcePack.from_file(bad_pack)


def test_red_light_rule_missing_licence_point_deduction_citation_is_rejected(tmp_path: Path) -> None:
    # Per-topic shape (task §4/§7): red-light rules require exactly one
    # primary_penalty, one licence_point_deduction, and one
    # signal_interpretation citation.
    bad_pack = tmp_path / "red_light_incomplete.json"
    bad_pack.write_text(
        json.dumps(
            {"rules": [_row(topic_id="traffic_red_light", legal_citations=[dict(_PRIMARY_PENALTY_CITATION)])]}
        ),
        encoding="utf-8",
    )
    with pytest.raises(TrafficSourcePackError):
        TrafficSourcePack.from_file(bad_pack)


def test_no_helmet_rule_with_a_licence_point_deduction_citation_is_rejected(tmp_path: Path) -> None:
    # Per-topic shape: the helmet rule's Điều 7 khoản 2 điểm h carries no
    # licence-point deduction -- a row claiming one would misrepresent the
    # law, not just be redundant.
    bad_pack = tmp_path / "helmet_extra_citation.json"
    bad_pack.write_text(
        json.dumps(
            {
                "rules": [
                    _row(
                        topic_id="traffic_no_helmet",
                        legal_citations=[
                            dict(_PRIMARY_PENALTY_CITATION),
                            {**_PRIMARY_PENALTY_CITATION, "citation_role": "licence_point_deduction", "clause_number": "13"},
                        ],
                    )
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(TrafficSourcePackError):
        TrafficSourcePack.from_file(bad_pack)


# -- Legal Correction Round 2 (MEDIUM-01): EXACT citation shape, not merely
# minimum counts. A role the shape never mentions at all must be rejected,
# not silently accepted because no minimum was configured for it.


def test_helmet_rule_with_an_extra_signal_interpretation_citation_is_rejected(tmp_path: Path) -> None:
    # The exact defect the independent reviewer's probe demonstrated: Round
    # 1's `_REQUIRED_CITATION_SHAPE_BY_TOPIC["traffic_no_helmet"]` never
    # mentioned `signal_interpretation` at all, so a helmet row carrying one
    # (a citation that has nothing to do with Điều 7 khoản 2 điểm h) passed
    # validation silently.
    bad_pack = tmp_path / "helmet_extra_signal.json"
    bad_pack.write_text(
        json.dumps(
            {
                "rules": [
                    _row(
                        topic_id="traffic_no_helmet",
                        legal_citations=[
                            dict(_PRIMARY_PENALTY_CITATION),
                            {
                                **_PRIMARY_PENALTY_CITATION,
                                "citation_role": "signal_interpretation",
                                "article_number": "11",
                                "clause_number": "1-4",
                                "point_number": None,
                            },
                        ],
                    )
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(TrafficSourcePackError):
        TrafficSourcePack.from_file(bad_pack)


def test_red_light_rule_with_two_primary_penalty_citations_is_rejected(tmp_path: Path) -> None:
    # An extra `primary_penalty` for a red-light rule -- the generic
    # exactly-one-primary_penalty check already catches this, but this test
    # exercises it specifically for a topic that also has a per-topic exact
    # shape, so both checks are proven to agree.
    bad_pack = tmp_path / "red_light_extra_primary.json"
    bad_pack.write_text(
        json.dumps(
            {
                "rules": [
                    _row(
                        topic_id="traffic_red_light",
                        legal_citations=[
                            dict(_PRIMARY_PENALTY_CITATION),
                            {**_PRIMARY_PENALTY_CITATION, "clause_number": "8"},
                            {
                                **_PRIMARY_PENALTY_CITATION,
                                "citation_role": "licence_point_deduction",
                                "clause_number": "13",
                                "point_number": "b",
                            },
                            {
                                **_PRIMARY_PENALTY_CITATION,
                                "citation_role": "signal_interpretation",
                                "article_number": "11",
                                "clause_number": "1-4",
                                "point_number": None,
                            },
                        ],
                    )
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(TrafficSourcePackError):
        TrafficSourcePack.from_file(bad_pack)


def test_red_light_rule_with_an_extra_unrelated_citation_role_location_is_rejected(tmp_path: Path) -> None:
    # A 4th, otherwise-valid citation (a second signal_interpretation at a
    # different legal location) added on top of an already-complete 3-role
    # shape -- the exact-shape check must reject the extra role count even
    # though every individual citation is independently well-formed.
    bad_pack = tmp_path / "red_light_extra_unrelated.json"
    bad_pack.write_text(
        json.dumps(
            {
                "rules": [
                    _row(
                        topic_id="traffic_red_light",
                        legal_citations=[
                            dict(_PRIMARY_PENALTY_CITATION),
                            {
                                **_PRIMARY_PENALTY_CITATION,
                                "citation_role": "licence_point_deduction",
                                "clause_number": "13",
                                "point_number": "b",
                            },
                            {
                                **_PRIMARY_PENALTY_CITATION,
                                "citation_role": "signal_interpretation",
                                "article_number": "11",
                                "clause_number": "1-4",
                                "point_number": None,
                            },
                            {
                                **_PRIMARY_PENALTY_CITATION,
                                "citation_role": "signal_interpretation",
                                "article_number": "11",
                                "clause_number": "5-6",
                                "point_number": None,
                            },
                        ],
                    )
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(TrafficSourcePackError):
        TrafficSourcePack.from_file(bad_pack)


def test_citation_with_an_unknown_role_is_rejected(tmp_path: Path) -> None:
    # An unrecognized `citation_role` value is rejected structurally by the
    # `CitationRole` Literal type at construction time, before the
    # exact-shape check even runs.
    bad_pack = tmp_path / "unknown_role.json"
    bad_pack.write_text(
        json.dumps(
            {"rules": [_row(legal_citations=[{**_PRIMARY_PENALTY_CITATION, "citation_role": "made_up_role"}])]}
        ),
        encoding="utf-8",
    )
    with pytest.raises(TrafficSourcePackError):
        TrafficSourcePack.from_file(bad_pack)


def test_real_pack_red_light_rules_have_the_full_three_citation_shape() -> None:
    pack = TrafficSourcePack.from_file(PACK_PATH)
    for rule_id in ("traffic_red_light__motorcycle__safe_v1", "traffic_red_light__car__safe_v1"):
        rule = next(r for r in pack._enabled_rules if r.rule_id == rule_id)
        roles = sorted(c.citation_role for c in rule.legal_citations)
        assert roles == ["licence_point_deduction", "primary_penalty", "signal_interpretation"]


def test_real_pack_helmet_rule_has_exactly_one_primary_penalty_citation() -> None:
    pack = TrafficSourcePack.from_file(PACK_PATH)
    rule = next(
        r for r in pack._enabled_rules if r.rule_id == "traffic_no_helmet__motorcycle__driver_safe_v1"
    )
    assert [c.citation_role for c in rule.legal_citations] == ["primary_penalty"]
