"""VietLaw Public Beta V0: trust-level contract (task §4 / §13.4).

Exact-string pinning for the required Vietnamese labels, plus the
evidence-outcome -> trust-level mapping invariant: only SUFFICIENT may ever
become OFFICIAL_SOURCE_SEARCH.
"""

from __future__ import annotations

from backend_lite.app.contracts.legal_trust import (
    EVIDENCE_OUTCOME_TRUST_LEVEL,
    EvidenceOutcome,
    TrustLevel,
    trust_explanation,
    trust_label,
)


# -- 1: exact required Vietnamese labels (task §4) ---------------------------

def test_curated_verified_label_is_exact() -> None:
    assert trust_label(TrustLevel.CURATED_VERIFIED) == "Đã kiểm chứng trong dữ liệu VietLaw"


def test_official_source_search_label_is_exact() -> None:
    assert trust_label(TrustLevel.OFFICIAL_SOURCE_SEARCH) == "Tra cứu từ nguồn pháp luật chính thức"


def test_general_guidance_label_is_exact() -> None:
    assert trust_label(TrustLevel.GENERAL_GUIDANCE) == "Hướng dẫn chung, chưa đủ căn cứ kết luận"


# -- 2: every level has a non-empty explanation ------------------------------

def test_every_trust_level_has_a_non_empty_explanation() -> None:
    for level in TrustLevel:
        assert trust_explanation(level).strip()


# -- 3: only SUFFICIENT maps to OFFICIAL_SOURCE_SEARCH -----------------------

def test_only_sufficient_outcome_maps_to_official_source_search() -> None:
    assert EVIDENCE_OUTCOME_TRUST_LEVEL[EvidenceOutcome.SUFFICIENT] is TrustLevel.OFFICIAL_SOURCE_SEARCH


def test_insufficient_conflicting_and_unavailable_all_map_to_general_guidance() -> None:
    for outcome in (EvidenceOutcome.INSUFFICIENT, EvidenceOutcome.CONFLICTING, EvidenceOutcome.UNAVAILABLE):
        assert EVIDENCE_OUTCOME_TRUST_LEVEL[outcome] is TrustLevel.GENERAL_GUIDANCE


# -- 4: the three trust levels are textually distinct (no shared appearance) -

def test_the_three_labels_are_all_distinct_strings() -> None:
    labels = {trust_label(level) for level in TrustLevel}
    assert len(labels) == 3


def test_the_three_explanations_are_all_distinct_strings() -> None:
    explanations = {trust_explanation(level) for level in TrustLevel}
    assert len(explanations) == 3
