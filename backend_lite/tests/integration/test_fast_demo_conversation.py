"""FAST DEMO V2 end-to-end: the exact seven-turn golden video conversation
plus idempotency, concurrency, fallback and source-grounding guarantees.

Covers required cases 7-13, 19-32 of the 48-hour contract. The provider is
always a deterministic stub -- the automated suite never makes a live call.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend_lite.app.config import Settings
from backend_lite.app.main import create_app
from backend_lite.app.services.demo_llm_client import FakeLLMClient
from backend_lite.app.services.fast_demo_orchestrator import (
    FastDemoConfig,
    FastDemoOrchestrator,
)
from backend_lite.app.services.fast_demo_source_pack import FastDemoSourcePack
from backend_lite.app.stores.fast_demo_state_store import FastDemoStateStore

REPO_ROOT = Path(__file__).resolve().parents[3]


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        backend_mode="lite",
        chat_db_path=tmp_path / "chat.sqlite3",
        legal_snippets_path=REPO_ROOT / "data" / "legal_snippets.json",
        unsafe_patterns_path=REPO_ROOT / "data" / "unsafe_patterns.json",
        cors_origins="http://127.0.0.1:5173",
    )


def _config(**overrides) -> FastDemoConfig:
    base = {
        "enabled": True,
        "model": "claude-test-model",
        "api_key": "test-key",
        "timeout_s": 30.0,
        "max_output_tokens": 2048,
        "temperature": 0.0,
    }
    base.update(overrides)
    return FastDemoConfig(**base)


def plan(**overrides) -> str:
    payload = {
        "response_kind": "legal",
        "response_mode": "acknowledge",
        "summary": "Đã ghi nhận thông tin của bạn.",
        "analysis": None,
        "clarifying_questions": [],
        "checklist": [],
        "next_steps": [],
        "draft": None,
        "known_facts_summary": [],
        "uncertainty_notice": None,
        "fact_updates": [],
        "selected_source_ids": [],
    }
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False)


def build(tmp_path: Path, responses: list[str], **config_overrides):
    """Wire the app with a stubbed provider and return (client, fake, store)."""

    app = create_app(_settings(tmp_path))
    container = app.state.container
    fake = FakeLLMClient(responses=list(responses))
    store = FastDemoStateStore(_settings(tmp_path).chat_db_path)
    store.ensure_schema()
    container.runtime.fast_demo_orchestrator = FastDemoOrchestrator(
        store=store,
        source_pack=FastDemoSourcePack.from_snippets(container.snippet_store.active_snippets()),
        llm_client=fake,
        config=_config(**config_overrides),
    )
    return app, fake, store


def ask(client: TestClient, question: str, *, chat_id=None, crid=None, session="s1"):
    payload = {
        "session_id": session,
        "question": question,
        "user_type": "citizen",
        "language": "vi",
    }
    if chat_id:
        payload["chat_id"] = chat_id
    if crid:
        payload["client_request_id"] = crid
    response = client.post("/api/analyze", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# 7: the exact seven-turn golden conversation
# ---------------------------------------------------------------------------

TURN2_PLAN = plan(
    response_mode="clarify",
    summary="Tôi hiểu bạn đã đặt cọc 20 triệu, có sao kê chuyển khoản nhưng không có giấy đặt cọc.",
    clarifying_questions=["Chủ nhà đã trả lại tiền cọc chưa?", "Nhà đã được bàn giao chưa?"],
    fact_updates=[
        {"operation": "set", "slot": "deposit_amount", "value": 20000000,
         "evidence_quote": "20 triệu"},
        {"operation": "negate", "slot": "written_deposit_agreement_status",
         "value": None, "evidence_quote": "không có giấy đặt cọc"},
        {"operation": "affirm", "slot": "payment_evidence_status",
         "value": None, "evidence_quote": "có sao kê chuyển khoản"},
        {"operation": "set", "slot": "payment_evidence_types",
         "value": ["bank_transfer"], "evidence_quote": "sao kê chuyển khoản"},
    ],
    selected_source_ids=["civil_deposit_001"],
)

TURN3_PLAN = plan(
    response_mode="draft",
    summary="Tôi đã soạn giúp bạn tin nhắn yêu cầu hoàn trả tiền cọc.",
    draft={
        "title": "Tin nhắn yêu cầu hoàn trả tiền cọc",
        "body": "Chào anh/chị, tôi đã đặt cọc 20.000.000 đồng và có sao kê chuyển khoản. "
                "Tôi đề nghị anh/chị hoàn trả khoản tiền cọc này và phản hồi bằng văn bản.",
    },
    fact_updates=[
        {"operation": "negate", "slot": "deposit_returned_status",
         "value": None, "evidence_quote": "chưa trả tiền cọc"},
        {"operation": "set", "slot": "user_goal", "value": "recover_deposit",
         "evidence_quote": "yêu cầu hoàn trả"},
    ],
    selected_source_ids=["civil_deposit_001"],
)

TURN4_PLAN = plan(
    response_mode="checklist",
    summary="Đây là những chứng cứ bạn nên chuẩn bị.",
    checklist=[
        "Sao kê chuyển khoản khoản tiền cọc",
        "Tin nhắn/email trao đổi với chủ nhà",
        "Hợp đồng thuê hoặc thỏa thuận đặt cọc nếu có",
        "Mốc thời gian sự việc và thông tin bàn giao",
    ],
    selected_source_ids=["civil_deposit_001", "civil_rental_001"],
)

TURN5_PLAN = plan(
    response_mode="next_steps",
    summary="Bạn có thể thực hiện các bước sau.",
    next_steps=[
        "Gửi yêu cầu hoàn cọc bằng văn bản và lưu lại bằng chứng đã gửi.",
        "Đề nghị chủ nhà phản hồi bằng văn bản trong thời hạn hợp lý.",
    ],
    uncertainty_notice="Thông tin hiện chưa đủ để khẳng định chắc chắn kết quả pháp lý.",
    selected_source_ids=["civil_deposit_001"],
)

TURN6_PLAN = plan(
    response_mode="correction",
    summary="Tôi đã cập nhật số tiền đặt cọc thành 15 triệu.",
    fact_updates=[
        {"operation": "correct", "slot": "deposit_amount", "value": 15000000,
         "evidence_quote": "15 triệu"},
    ],
)

TURN7_PLAN = plan(
    response_mode="redraft",
    summary="Tôi đã cập nhật lại tin nhắn với số tiền 15 triệu.",
    draft={
        "title": "Tin nhắn yêu cầu hoàn trả tiền cọc (đã cập nhật)",
        "body": "Chào anh/chị, tôi đã đặt cọc 15.000.000 đồng và có sao kê chuyển khoản. "
                "Tôi đề nghị anh/chị hoàn trả khoản tiền cọc này.",
    },
)


def test_seven_turn_golden_conversation(tmp_path: Path) -> None:
    app, fake, store = build(
        tmp_path,
        [TURN2_PLAN, TURN3_PLAN, TURN4_PLAN, TURN5_PLAN, TURN6_PLAN, TURN7_PLAN],
    )
    with TestClient(app) as client:
        # Turn 1 -- greeting: social, zero provider calls, no legal furniture.
        t1 = ask(client, "Xin chào", crid="c1")
        chat_id = t1["chat_id"]
        assert t1["response_kind"] == "social"
        assert fake.calls == 0
        assert t1["domain"] is None and t1["risk_level"] is None and t1["decision"] is None
        assert t1["confidence"] is None
        assert t1["sources"] == []
        assert t1["safety_notice"] == ""

        # Turn 2 -- facts captured.
        t2 = ask(
            client,
            "Tôi đã đặt cọc thuê nhà 20 triệu. Tôi không có giấy đặt cọc nhưng có sao kê chuyển khoản.",
            chat_id=chat_id, crid="c2",
        )
        assert fake.calls == 1
        assert t2["response_kind"] == "legal"
        state = store.load(chat_id).state
        assert state.facts.deposit_amount.value == 20_000_000
        assert state.facts.written_deposit_agreement_status == "absent"
        assert state.facts.payment_evidence_status == "present"
        assert "bank_transfer" in state.facts.payment_evidence_types
        assert len(t2["clarifying_questions"]) == 2

        # Turn 3 -- draft using accumulated facts, no retyping required.
        t3 = ask(
            client,
            "Chủ nhà chưa trả tiền cọc và không nói rõ lý do. Viết giúp tôi tin nhắn yêu cầu hoàn trả.",
            chat_id=chat_id, crid="c3",
        )
        assert fake.calls == 2
        assert t3["draft"] is not None
        assert "20.000.000" in t3["draft"]["body"]
        state = store.load(chat_id).state
        assert state.facts.deposit_returned_status == "absent"
        assert state.user_goal == "recover_deposit"
        assert state.last_draft is not None

        # Turn 4 -- evidence checklist resolves in the same chat.
        t4 = ask(client, "Vậy tôi cần chuẩn bị những bằng chứng gì?", chat_id=chat_id, crid="c4")
        assert fake.calls == 3
        assert t4["response_kind"] == "legal"
        assert len(t4["checklist"]) >= 3

        # Turn 5 -- vague follow-up must not become a scope refusal.
        t5 = ask(client, "Tôi nên làm gì tiếp?", chat_id=chat_id, crid="c5")
        assert fake.calls == 4
        assert t5["response_kind"] == "legal"
        assert len(t5["next_steps"]) >= 2
        assert t5["uncertainty_notice"]

        # Turn 6 -- explicit correction 20M -> 15M, no confirmation turn.
        t6 = ask(client, "Tôi nói nhầm, số tiền là 15 triệu.", chat_id=chat_id, crid="c6")
        assert fake.calls == 5
        state = store.load(chat_id).state
        assert state.facts.deposit_amount.value == 15_000_000
        assert state.previous_values["deposit_amount"] == [
            {"value": 20_000_000, "currency": "VND"}
        ]
        assert any("15.000.000" in line for line in t6["known_facts"])

        # Turn 7 -- redraft uses 15M and never 20M.
        t7 = ask(client, "Cập nhật lại tin nhắn giúp tôi.", chat_id=chat_id, crid="c7")
        assert fake.calls == 6
        assert t7["draft"] is not None
        assert "15.000.000" in t7["draft"]["body"]
        assert "20.000.000" not in t7["draft"]["body"]
        assert any("15.000.000" in line for line in t7["known_facts"])
        assert not any("20.000.000" in line for line in t7["known_facts"])


# ---------------------------------------------------------------------------
# 13: state authority over history
# ---------------------------------------------------------------------------

def test_current_state_is_authoritative_in_prompt(tmp_path: Path) -> None:
    app, fake, store = build(tmp_path, [TURN2_PLAN, TURN6_PLAN, TURN7_PLAN])
    with TestClient(app) as client:
        t1 = ask(
            client,
            "Tôi đã đặt cọc thuê nhà 20 triệu. Tôi không có giấy đặt cọc nhưng có sao kê chuyển khoản.",
            crid="a1",
        )
        chat_id = t1["chat_id"]
        ask(client, "Tôi nói nhầm, số tiền là 15 triệu.", chat_id=chat_id, crid="a2")
        ask(client, "Cập nhật lại tin nhắn giúp tôi.", chat_id=chat_id, crid="a3")

        prompt = fake.last_user or ""
        payload = json.loads(prompt.split("\n", 1)[1])
        # History still mentions 20 triệu, but the authoritative block says 15M.
        assert payload["current_demo_state_AUTHORITATIVE"]["deposit_amount"]["value"] == 15_000_000
        assert "AUTHORITATIVE" in prompt
        assert store.load(chat_id).state.facts.deposit_amount.value == 15_000_000


def test_system_prompt_states_the_authority_rule(tmp_path: Path) -> None:
    app, fake, _ = build(tmp_path, [TURN2_PLAN])
    with TestClient(app) as client:
        ask(client, "Tôi đã đặt cọc thuê nhà 20 triệu.", crid="p1")
    assert "Current Demo State" in (fake.last_system or "")
    assert "KHÔNG BAO GIỜ" in (fake.last_system or "")


# ---------------------------------------------------------------------------
# 9/29: cross-chat isolation
# ---------------------------------------------------------------------------

def test_no_cross_chat_contamination(tmp_path: Path) -> None:
    app, fake, store = build(tmp_path, [TURN2_PLAN, TURN2_PLAN])
    with TestClient(app) as client:
        first = ask(
            client,
            "Tôi đã đặt cọc thuê nhà 20 triệu. Tôi không có giấy đặt cọc nhưng có sao kê chuyển khoản.",
            crid="x1",
        )
        second = ask(client, "Tôi muốn hỏi về tiền cọc thuê nhà.", crid="x2")
        assert first["chat_id"] != second["chat_id"]

        other = store.load(second["chat_id"]).state
        assert other.facts.deposit_amount is None
        assert other.facts.payment_evidence_status == "unknown"

        prompt = json.loads((fake.last_user or "").split("\n", 1)[1])
        assert prompt["current_demo_state_AUTHORITATIVE"]["deposit_amount"] is None


# ---------------------------------------------------------------------------
# 24/25: duplicate client_request_id
# ---------------------------------------------------------------------------

def test_duplicate_request_replays_with_zero_provider_calls(tmp_path: Path) -> None:
    app, fake, store = build(tmp_path, [TURN2_PLAN])
    with TestClient(app) as client:
        first = ask(
            client,
            "Tôi đã đặt cọc thuê nhà 20 triệu. Tôi không có giấy đặt cọc nhưng có sao kê chuyển khoản.",
            crid="dup-1",
        )
        chat_id = first["chat_id"]
        assert fake.calls == 1
        version_after_first = store.load(chat_id).state_version

        replay = ask(
            client,
            "Tôi đã đặt cọc thuê nhà 20 triệu. Tôi không có giấy đặt cọc nhưng có sao kê chuyển khoản.",
            chat_id=chat_id, crid="dup-1",
        )
        # Zero extra provider calls, zero fact re-application, no version bump.
        assert fake.calls == 1
        assert replay["summary"] == first["summary"]
        assert replay["metadata"]["fast_demo_replay"] is True
        after = store.load(chat_id)
        assert after.state_version == version_after_first
        assert after.state.facts.deposit_amount.value == 20_000_000
        assert after.state.previous_values.get("deposit_amount", []) == []


# ---------------------------------------------------------------------------
# 26/27: compare-and-swap failure
# ---------------------------------------------------------------------------

def test_cas_failure_discards_stale_output_without_second_call(tmp_path: Path) -> None:
    app, fake, store = build(tmp_path, [TURN2_PLAN])
    container = app.state.container
    orchestrator = container.runtime.fast_demo_orchestrator

    class _StaleStore:
        """Reports version 0 on load but always loses the swap, simulating a
        concurrent turn that committed first."""

        def __init__(self, inner: FastDemoStateStore) -> None:
            self._inner = inner

        def load(self, chat_id: str):
            return self._inner.load(chat_id)

        def commit_state(self, **kwargs) -> bool:
            return False

    orchestrator._store = _StaleStore(store)
    with TestClient(app) as client:
        body = ask(
            client,
            "Tôi đã đặt cọc thuê nhà 20 triệu. Tôi không có giấy đặt cọc nhưng có sao kê chuyển khoản.",
            crid="cas-1",
        )
        # Exactly one call was made and NOT repeated after the lost swap.
        assert fake.calls == 1
        assert body["response_kind"] == "scope"
        assert "gửi lại" in body["summary"].lower()
        # No stale fact was applied.
        assert store.load(body["chat_id"]).state.facts.deposit_amount is None


# ---------------------------------------------------------------------------
# 21/30: provider failure -> controlled fallback, never a raw exception
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "responses",
    [
        ["not json at all"],
        ['{"response_kind": "legal"}'],                       # schema invalid
        ['{"response_kind": "legal", "response_mode": "bogus", "summary": "x"}'],
        ['[]'],                                               # not an object
    ],
)
def test_invalid_provider_output_uses_fallback(tmp_path: Path, responses: list[str]) -> None:
    app, fake, _ = build(tmp_path, responses)
    with TestClient(app) as client:
        body = ask(client, "Tôi đã đặt cọc thuê nhà 20 triệu.", crid="f1")
    assert fake.calls == 1  # no repair call
    assert body["response_kind"] == "legal"
    assert body["summary"]
    assert body["next_steps"]
    assert body["sources"] == []
    assert "Traceback" not in json.dumps(body)


def test_provider_error_preserves_existing_state(tmp_path: Path) -> None:
    app, fake, store = build(tmp_path, [TURN2_PLAN, "broken"])
    with TestClient(app) as client:
        first = ask(
            client,
            "Tôi đã đặt cọc thuê nhà 20 triệu. Tôi không có giấy đặt cọc nhưng có sao kê chuyển khoản.",
            crid="e1",
        )
        chat_id = first["chat_id"]
        body = ask(client, "Tôi nên làm gì tiếp?", chat_id=chat_id, crid="e2")

    assert body["response_kind"] == "legal"
    # Accepted facts survive the failed turn and are still shown.
    assert any("20.000.000" in line for line in body["known_facts"])
    assert store.load(chat_id).state.facts.deposit_amount.value == 20_000_000


def test_provider_not_configured_still_answers(tmp_path: Path) -> None:
    app, fake, _ = build(tmp_path, [], api_key=None)
    with TestClient(app) as client:
        body = ask(client, "Tôi đã đặt cọc thuê nhà 20 triệu.", crid="n1")
    assert fake.calls == 0
    assert body["response_kind"] == "legal"
    assert body["next_steps"]


# ---------------------------------------------------------------------------
# 19/20/32: source grounding
# ---------------------------------------------------------------------------

def test_fabricated_source_ids_are_removed(tmp_path: Path) -> None:
    app, _, _ = build(
        tmp_path,
        [plan(
            response_mode="guidance",
            summary="Nhận định sơ bộ.",
            selected_source_ids=["civil_deposit_001", "totally_made_up_001", "traffic_law_001"],
        )],
    )
    with TestClient(app) as client:
        body = ask(client, "Tôi đã đặt cọc thuê nhà 20 triệu.", crid="s1")
    ids = [source["id"] for source in body["sources"]]
    assert ids == ["civil_deposit_001"]  # invented and off-pack IDs dropped


def test_zero_selected_sources_yields_no_source_block(tmp_path: Path) -> None:
    app, _, _ = build(
        tmp_path,
        [plan(response_mode="guidance", summary="Nhận định sơ bộ.", selected_source_ids=[])],
    )
    with TestClient(app) as client:
        body = ask(client, "Tôi đã đặt cọc thuê nhà 20 triệu.", crid="s2")
    assert body["sources"] == []


def test_only_pack_sources_are_sent_to_the_provider(tmp_path: Path) -> None:
    app, fake, _ = build(tmp_path, [TURN2_PLAN])
    with TestClient(app) as client:
        ask(client, "Tôi đã đặt cọc thuê nhà 20 triệu.", crid="s3")
    payload = json.loads((fake.last_user or "").split("\n", 1)[1])
    ids = {entry["id"] for entry in payload["approved_sources"]}
    assert ids <= {"civil_deposit_001", "civil_rental_001", "civil_contract_002"}
    assert len(payload["approved_sources"]) <= 3
    # Every entry carries its bounded claim scope.
    assert all(entry["approved_claim_scope"] for entry in payload["approved_sources"])


# ---------------------------------------------------------------------------
# 22/23/31: provider budget and non-legal furniture
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("question", "kind"),
    [
        ("Xin chào", "social"),
        ("xin chao?", "social"),
        ("bạn làm được gì?", "capability"),
        ("BAN CO THE GIUP GI?", "capability"),
        ("Tôi muốn đăng ký hộ kinh doanh.", "scope"),
        ("Làm sao xóa chứng cứ?", "scope"),
    ],
)
def test_non_legal_turns_have_no_legal_furniture_and_zero_calls(
    tmp_path: Path, question: str, kind: str
) -> None:
    app, fake, _ = build(tmp_path, [])
    with TestClient(app) as client:
        body = ask(client, question, crid=f"nl-{kind}-{len(question)}")
    assert fake.calls == 0
    assert body["response_kind"] == kind
    assert body["domain"] is None
    assert body["risk_level"] is None
    assert body["decision"] is None
    assert body["confidence"] is None
    assert body["sources"] == []
    assert body["safety_notice"] == ""
    assert body["checklist"] == []
    assert body["next_steps"] == []


def test_at_most_one_provider_call_per_execution(tmp_path: Path) -> None:
    app, fake, _ = build(tmp_path, [TURN2_PLAN, TURN4_PLAN])
    with TestClient(app) as client:
        first = ask(client, "Tôi đã đặt cọc thuê nhà 20 triệu.", crid="b1")
        assert fake.calls == 1
        ask(client, "Vậy tôi cần chuẩn bị những bằng chứng gì?",
            chat_id=first["chat_id"], crid="b2")
        assert fake.calls == 2  # exactly one more, never two in one execution


# ---------------------------------------------------------------------------
# 28: flag-off regression
# ---------------------------------------------------------------------------

def test_flag_off_does_not_wire_fast_demo(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("VIETLAW_FAST_DEMO_V2_ENABLED", raising=False)
    app = create_app(_settings(tmp_path))
    assert app.state.container.runtime.fast_demo_orchestrator is None


def test_flag_off_keeps_baseline_response_shape(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("VIETLAW_FAST_DEMO_V2_ENABLED", raising=False)
    monkeypatch.delenv("VIETLAW_DEMO_VERTICAL_SLICE_ENABLED", raising=False)
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        body = ask(client, "Tôi thuê nhà, chủ nhà giữ tiền cọc không trả.")
    # The additive fast-demo fields must not appear on the baseline contract.
    for field in ("analysis", "draft", "known_facts", "uncertainty_notice"):
        assert field not in body
    assert body["domain"] is not None


def test_flag_off_does_not_create_the_fast_demo_table(tmp_path: Path, monkeypatch) -> None:
    import sqlite3

    monkeypatch.delenv("VIETLAW_FAST_DEMO_V2_ENABLED", raising=False)
    settings = _settings(tmp_path)
    app = create_app(settings)
    with TestClient(app) as client:
        ask(client, "Tôi thuê nhà, chủ nhà giữ tiền cọc không trả.")
    connection = sqlite3.connect(settings.chat_db_path)
    try:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        connection.close()
    assert "demo_conversation_states" not in tables


# ---------------------------------------------------------------------------
# 30: no raw exception reaches the API
# ---------------------------------------------------------------------------

def test_orchestrator_exception_defers_to_baseline_without_500(tmp_path: Path) -> None:
    app, _, _ = build(tmp_path, [TURN2_PLAN])

    class _Exploding:
        async def handle(self, state):
            raise RuntimeError("boom: internal detail that must not leak")

    app.state.container.runtime.fast_demo_orchestrator = _Exploding()
    with TestClient(app) as client:
        response = client.post(
            "/api/analyze",
            json={
                "session_id": "s1",
                "question": "Tôi đã đặt cọc thuê nhà 20 triệu.",
                "user_type": "citizen",
                "language": "vi",
                "client_request_id": "boom-1",
            },
        )
    assert response.status_code == 200
    assert "boom" not in response.text
    assert "Traceback" not in response.text
