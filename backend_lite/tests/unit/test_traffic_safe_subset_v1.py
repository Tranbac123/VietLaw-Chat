"""Traffic Safe Subset V1: the exact required probe messages from task §9
and §10, exercised end to end through `LegalFallbackOrchestrator` (not just
`classify()`/`select_rule()` in isolation -- those are covered directly in
`test_traffic_classifier.py` and `test_traffic_source_pack.py`).

The independent legal review (`VIETLAW_PUBLIC_BETA_V0_TRAFFIC_LEGAL_ACCURACY_
REVIEW_V1.md`) blocked all 11 original rules; a subsequent targeted
re-review (`VIETLAW_TRAFFIC_SAFE_SUBSET_V1_LEGAL_REVIEW_V1.md`, Legal
Correction Round 1) then found Rule D (motorcycle hand-held phone use)
itself legally unsafe (HIGH-01: its selector could MATCH even when the user
explicitly denied USING the phone, holding it being a different legal
element from using it) and disabled it. This file asserts the twice-
corrected pack's behavior: exactly 3 verified rules (A: motorcycle red
light, B: car red light, C: motorcycle driver no-helmet) may ever emit
`curated_verified`, and the five disabled topics (alcohol, speeding,
driver_license, passenger_limit, vehicle_modification) plus phone_use plus
every unsupported subcase must always fail closed to `general_guidance`
with no penalty amount, no article citation, and no `clarifying_questions`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from backend_lite.app.services.legal_fallback_orchestrator import LegalFallbackOrchestrator
from backend_lite.app.services.traffic_source_pack import TrafficSourcePack
from backend_lite.app.stores.legal_fallback_state_store import LegalFallbackStateStore

REPO_ROOT = Path(__file__).resolve().parents[3]
TRAFFIC_PACK_PATH = REPO_ROOT / "data" / "traffic_rules.json"


@dataclass
class _FakeRequest:
    question: str
    request_id: str = "req-1"


@dataclass
class _FakeChat:
    chat_id: str


@dataclass
class _FakePersistence:
    user_message_id: str = "u1"
    assistant_message_id: str = "a1"


@dataclass
class _FakeState:
    request: _FakeRequest
    chat: _FakeChat = field(default_factory=lambda: _FakeChat(chat_id="chat-1"))
    persistence: _FakePersistence = field(default_factory=_FakePersistence)


def _state(question: str, chat_id: str = "chat-1") -> _FakeState:
    return _FakeState(request=_FakeRequest(question=question), chat=_FakeChat(chat_id=chat_id))


def _orchestrator(tmp_path: Path) -> LegalFallbackOrchestrator:
    pack = TrafficSourcePack.from_file(TRAFFIC_PACK_PATH)
    store = LegalFallbackStateStore(tmp_path / "legal_fallback.sqlite3")
    store.ensure_schema()
    return LegalFallbackOrchestrator(
        store=store, traffic_pack=pack, search_service=None, official_search_enabled=False
    )


def _assert_no_curated_answer(response) -> None:
    """Task §9's shared negative-test shape: whatever tier the message ends
    up on (deferred, a clarification ask, or general guidance), it must
    never carry a specific penalty amount, an article citation, or a
    concluded curated legal answer.

    Legal Correction Round 1 (MEDIUM-02): a clarification ASK now carries
    `trust_level=None` (never `curated_verified` -- it is a question, not a
    legal conclusion), so this reduces to one check regardless of which
    non-MATCH tier the message landed on."""

    if response is None:
        return
    assert response.trust_level != "curated_verified"
    assert response.sources == []


def _all_sources_blob(response) -> str:
    """Every enabled rule's legal support may now span multiple structured
    `legal_citations` (Legal Correction Round 1, MEDIUM-01) -- a citation
    text check must search all of `sources`, not just `sources[0]`.
    `relevance_note` (not `snippet`) carries the full "Điều X khoản Y điểm
    Z — ..." locator text for each citation."""

    return response.summary + " ".join(s.relevance_note or "" for s in response.sources)


# =============================================================================
# Rule A: motorcycle red light (task §3, §9)
# =============================================================================


@pytest.mark.asyncio
async def test_rule_a_positive_motorcycle_red_light(tmp_path: Path) -> None:
    orch = _orchestrator(tmp_path)
    response = await orch.handle(_state("Tôi đi xe máy vượt đèn đỏ, không gây tai nạn."))
    assert response is not None
    assert response.trust_level == "curated_verified"
    assert len(response.sources) == 3  # primary_penalty + licence_point_deduction + signal_interpretation
    blob = _all_sources_blob(response)
    assert "4.000.000" in blob and "6.000.000" in blob
    assert "4 điểm" in blob
    assert "Điều 7 khoản 7 điểm c" in blob
    assert "Điều 7 khoản 13 điểm b" in blob
    assert "Điều 11" in blob  # Luật 36/2024/QH15's signal-priority basis


@pytest.mark.parametrize(
    "message",
    [
        "Tôi đi theo hiệu lệnh của cảnh sát giao thông.",
        "Đèn chuyển vàng khi tôi đã qua vạch.",
        "Tôi vượt đèn và gây tai nạn.",
        "Tôi không nhớ đèn đỏ hay vàng.",
    ],
)
@pytest.mark.asyncio
async def test_rule_a_negative_and_ambiguous_probes(tmp_path: Path, message: str) -> None:
    orch = _orchestrator(tmp_path)
    response = await orch.handle(_state(message))
    _assert_no_curated_answer(response)


@pytest.mark.asyncio
async def test_rule_a_controller_override_excludes_via_the_selector(tmp_path: Path) -> None:
    # Exercises the exclusion through `select_rule` itself (not mere topic
    # non-detection): vehicle_type and signal_type are both determinable
    # from this one message, so it reaches NO_SAFE_RULE via the excluded
    # `traffic_controller_override="yes"` fact, never a curated answer.
    orch = _orchestrator(tmp_path)
    response = await orch.handle(
        _state("Tôi đi xe máy vượt đèn đỏ nhưng đi theo hiệu lệnh của cảnh sát giao thông.")
    )
    _assert_no_curated_answer(response)


@pytest.mark.asyncio
async def test_rule_a_yellow_excludes_via_the_selector(tmp_path: Path) -> None:
    orch = _orchestrator(tmp_path)
    response = await orch.handle(_state("Tôi đi xe máy vượt đèn nhưng đèn đang chuyển vàng."))
    _assert_no_curated_answer(response)


# =============================================================================
# Rule B: car red light (task §3, §9)
# =============================================================================


@pytest.mark.asyncio
async def test_rule_b_positive_car_red_light(tmp_path: Path) -> None:
    orch = _orchestrator(tmp_path)
    response = await orch.handle(_state("Tôi lái ô tô vượt đèn đỏ."))
    assert response is not None
    assert response.trust_level == "curated_verified"
    assert len(response.sources) == 3
    blob = _all_sources_blob(response)
    assert "18.000.000" in blob and "20.000.000" in blob
    assert "4 điểm" in blob
    assert "Điều 6 khoản 9 điểm b" in blob
    assert "Điều 6 khoản 16 điểm b" in blob
    assert "Điều 11" in blob


@pytest.mark.parametrize(
    "message",
    [
        "Tôi lái ô tô và đi theo hiệu lệnh của cảnh sát giao thông.",
        "Ô tô của tôi vượt đèn khi đèn đã chuyển vàng.",
        "Tôi lái ô tô vượt đèn và gây tai nạn.",
    ],
)
@pytest.mark.asyncio
async def test_rule_b_negative_probes(tmp_path: Path, message: str) -> None:
    orch = _orchestrator(tmp_path)
    response = await orch.handle(_state(message))
    _assert_no_curated_answer(response)


# =============================================================================
# Rule C: motorcycle driver, no helmet (task §3, §9)
# =============================================================================


@pytest.mark.asyncio
async def test_rule_c_positive_not_wearing(tmp_path: Path) -> None:
    orch = _orchestrator(tmp_path)
    response = await orch.handle(_state("Tôi lái xe máy nhưng không đội mũ bảo hiểm."))
    assert response is not None
    assert response.trust_level == "curated_verified"
    assert len(response.sources) == 1  # no licence-point deduction for Điều 7 khoản 2 điểm h
    assert response.sources[0].citation_role == "primary_penalty"
    blob = response.summary + response.sources[0].snippet
    assert "400.000" in blob and "600.000" in blob
    assert "Điều 7 khoản 2 điểm h" in blob


@pytest.mark.asyncio
async def test_rule_c_positive_improperly_fastened_resolves_after_vehicle_type(tmp_path: Path) -> None:
    orch = _orchestrator(tmp_path)
    chat_id = "chat-c-strap"
    first = await orch.handle(_state("Tôi đội mũ nhưng không cài quai.", chat_id))
    assert first is not None
    second = await orch.handle(_state("Xe máy.", chat_id))
    assert second is not None
    assert second.trust_level == "curated_verified"
    assert "400.000" in second.summary


@pytest.mark.parametrize(
    "message",
    [
        "Người ngồi sau không đội mũ bảo hiểm.",
        "Tôi chở trẻ em không đội mũ.",
        "Tôi có đội mũ đúng quy cách.",
    ],
)
@pytest.mark.asyncio
async def test_rule_c_negative_probes(tmp_path: Path, message: str) -> None:
    orch = _orchestrator(tmp_path)
    response = await orch.handle(_state(message))
    _assert_no_curated_answer(response)


@pytest.mark.asyncio
async def test_rule_c_passenger_excludes_via_the_selector(tmp_path: Path) -> None:
    # All three required facts (vehicle_type, helmet_subject, helmet_status)
    # are determinable from one message, so this reaches NO_SAFE_RULE via
    # the excluded `helmet_subject="passenger"` fact, never non-detection.
    orch = _orchestrator(tmp_path)
    response = await orch.handle(
        _state("Tôi lái xe máy, người ngồi sau không đội mũ bảo hiểm.")
    )
    _assert_no_curated_answer(response)


# =============================================================================
# Rule D: motorcycle, hand-held phone use -- DISABLED (Legal Correction
# Round 1, HIGH-01). The selector's required facts (phone_handheld=yes,
# vehicle_in_operation=yes) proved only that the rider was holding the
# device while the vehicle moved, not the separate legal element of
# Điều 7 khoản 4 điểm đ, "sử dụng điện thoại" (actually USING it). Every
# probe below -- including the ones that would have MATCHED the
# pre-correction selector -- must now fall to general_guidance.
# =============================================================================


@pytest.mark.parametrize(
    "message",
    [
        "Tôi dùng tay cầm điện thoại khi đang chạy xe máy.",
        # Legal Correction Round 2 (LOW-02): the FULL verbatim HIGH-01
        # adversarial probe -- the shorter "Tôi cầm điện thoại nhưng chưa
        # sử dụng điện thoại." below is an equivalent, not this exact
        # sentence; both are tested here so no report/coverage description
        # mismatch survives.
        "Tôi dùng tay cầm điện thoại khi đang chạy xe máy nhưng chưa sử dụng điện thoại.",
        "Tôi cầm điện thoại nhưng chưa sử dụng điện thoại.",  # shorter equivalent probe
        "Tôi dùng tai nghe rảnh tay.",
        "Điện thoại gắn trên giá đỡ.",
        "Tôi dùng điện thoại khi xe đã dừng.",
        "Tôi dùng điện thoại khi lái ô tô.",
    ],
)
@pytest.mark.asyncio
async def test_rule_d_disabled_never_produces_a_curated_answer(tmp_path: Path, message: str) -> None:
    orch = _orchestrator(tmp_path)
    response = await orch.handle(_state(message))
    _assert_no_curated_answer(response)


@pytest.mark.asyncio
async def test_rule_d_disabled_falls_through_to_general_guidance_with_no_citation(tmp_path: Path) -> None:
    orch = _orchestrator(tmp_path)
    response = await orch.handle(_state("Tôi dùng tay cầm điện thoại khi đang chạy xe máy."))
    assert response is not None
    assert response.trust_level == "general_guidance"
    assert response.clarifying_questions == []
    assert response.sources == []
    assert "800.000" not in response.summary
    assert "Điều 7" not in response.summary


# =============================================================================
# Disabled-rule tests (task §9, exact required probes)
# =============================================================================


@pytest.mark.parametrize(
    "message",
    [
        "0.2 mg/l khí thở",
        "vượt tốc độ 10 km/h",
        "quên mang bằng lái",
        "chở 3 người",
        "thay lốp nhỏ",
    ],
)
@pytest.mark.asyncio
async def test_disabled_topic_probes_are_general_guidance_with_no_citation(tmp_path: Path, message: str) -> None:
    orch = _orchestrator(tmp_path)
    response = await orch.handle(_state(message))
    assert response is not None
    assert response.trust_level == "general_guidance"
    assert response.clarifying_questions == []
    assert response.sources == []
    # specific_penalty_absent / article_citation_absent
    assert "Điều" not in response.summary
    assert "đồng" not in response.summary


# =============================================================================
# Trust-level gating (task §7)
# =============================================================================


@pytest.mark.asyncio
async def test_curated_verified_never_appears_without_all_gating_conditions(tmp_path: Path) -> None:
    orch = _orchestrator(tmp_path)
    # A MATCH always carries a primary URL and full citation metadata
    # (enforced at pack-load time by `TrafficSourcePack.from_file`).
    response = await orch.handle(_state("Tôi đi xe máy vượt đèn đỏ."))
    assert response.trust_level == "curated_verified"
    assert response.sources[0].url.startswith("https://vbpl.vn/")
    assert response.sources[0].article_number is not None


@pytest.mark.asyncio
async def test_general_guidance_never_carries_sources_or_specific_penalty(tmp_path: Path) -> None:
    orch = _orchestrator(tmp_path)
    response = await orch.handle(_state("Tôi vượt đèn và gây tai nạn khi đi xe máy."))
    assert response is not None
    assert response.trust_level == "general_guidance"
    assert response.sources == []


# =============================================================================
# Adversarial / conversation tests (task §10)
# =============================================================================


@pytest.mark.asyncio
async def test_fresh_traffic_topic_while_a_different_topic_is_pending_switches_immediately(
    tmp_path: Path,
) -> None:
    orch = _orchestrator(tmp_path)
    chat_id = "chat-topic-switch"
    first = await orch.handle(_state("Tôi vượt đèn đỏ thì bị phạt bao nhiêu?", chat_id))
    assert first.clarifying_questions == ["Bạn điều khiển xe máy hay ô tô?"]
    loaded = orch._store.load(chat_id)
    assert loaded.state.traffic_topic_id == "traffic_red_light"

    # A brand-new, fully self-contained topic in the SAME chat -- must
    # resolve on its own terms, never be misread as an answer to the old
    # "xe máy hay ô tô?" question.
    second = await orch.handle(
        _state("Tôi lái xe máy nhưng không đội mũ bảo hiểm.", chat_id)
    )
    assert second is not None
    assert second.trust_level == "curated_verified"
    assert "400.000" in second.summary

    loaded = orch._store.load(chat_id)
    assert loaded.state.traffic_topic_id is None
    assert loaded.state.traffic_pending_field is None


@pytest.mark.asyncio
async def test_third_party_facts_never_persist_across_the_chat(tmp_path: Path) -> None:
    orch = _orchestrator(tmp_path)
    chat_id = "chat-adversarial-third-party"
    response = await orch.handle(
        _state("Bạn tôi dùng tay cầm điện thoại khi đang chạy xe máy.", chat_id)
    )
    assert response is not None
    loaded = orch._store.load(chat_id)
    assert loaded is None or loaded.state.traffic_facts.vehicle_type == "unknown"
    assert loaded is None or loaded.state.traffic_facts.phone_handheld == "unknown"


@pytest.mark.asyncio
async def test_hypothetical_facts_never_persist_across_the_chat(tmp_path: Path) -> None:
    orch = _orchestrator(tmp_path)
    chat_id = "chat-adversarial-hypothetical"
    response = await orch.handle(
        _state("Nếu một người đi xe máy vượt đèn đỏ thì bị phạt sao?", chat_id)
    )
    assert response is not None
    loaded = orch._store.load(chat_id)
    assert loaded is None or loaded.state.traffic_facts.vehicle_type == "unknown"


@pytest.mark.asyncio
async def test_negated_facts_never_persist_and_never_answer_as_curated(tmp_path: Path) -> None:
    orch = _orchestrator(tmp_path)
    chat_id = "chat-adversarial-negated"
    response = await orch.handle(_state("Tôi không vượt đèn đỏ khi đi xe máy.", chat_id))
    assert response is None
    loaded = orch._store.load(chat_id)
    assert loaded is None or loaded.state.traffic_facts.vehicle_type == "unknown"
