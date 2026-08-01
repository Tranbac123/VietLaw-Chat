"""VietLaw Public Beta V0: end-to-end routing, safety precedence, and the
wire-level trust contract, exercised through the real FastAPI app (task §3,
§4, §9, §13.4). No live network: official-source search stays disabled by
default (`VIETLAW_OFFICIAL_LEGAL_SEARCH_ENABLED` unset), so these turns only
ever reach the curated-traffic and general-guidance tiers.

The legal-fallback vertical is only ever consulted once FAST DEMO V2 has
declined a turn as out of its own scope (see `agent_runtime.py`'s hook), so
-- exactly like `test_phase_b_short_messages_and_context.py` -- a
`FakeLLMClient`-backed `FastDemoOrchestrator` is wired explicitly here. None
of the messages below are deposit-shaped, so `classify_route` resolves them
deterministically to SCOPE/UNSAFE without ever invoking the fake LLM.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend_lite.app.config import Settings
from backend_lite.app.main import create_app
from backend_lite.app.services.demo_llm_client import FakeLLMClient
from backend_lite.app.services.fast_demo_orchestrator import FastDemoConfig, FastDemoOrchestrator
from backend_lite.app.services.fast_demo_source_pack import FastDemoSourcePack
from backend_lite.app.stores.fast_demo_state_store import FastDemoStateStore

REPO_ROOT = Path(__file__).resolve().parents[3]


def _app(tmp_path: Path):
    settings = Settings(
        backend_mode="lite",
        chat_db_path=tmp_path / "chat.sqlite3",
        cors_origins="http://127.0.0.1:5173",
    )
    app = create_app(settings)
    container = app.state.container
    store = FastDemoStateStore(tmp_path / "fast_demo.sqlite3")
    store.ensure_schema()
    container.runtime.fast_demo_orchestrator = FastDemoOrchestrator(
        store=store,
        source_pack=FastDemoSourcePack.from_snippets(container.snippet_store.active_snippets()),
        llm_client=FakeLLMClient(responses=[]),
        config=FastDemoConfig(
            enabled=True,
            model="claude-test-model",
            api_key="test-key",
            timeout_s=30.0,
            max_output_tokens=2048,
            temperature=0.0,
        ),
    )
    return app


def ask(client: TestClient, question: str, *, chat_id=None, session="s1"):
    payload = {"session_id": session, "question": question}
    if chat_id:
        payload["chat_id"] = chat_id
    response = client.post("/api/analyze", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


# -- routing precedence (task §3) --------------------------------------------

def test_existing_deposit_matter_never_reaches_the_legal_fallback(tmp_path: Path) -> None:
    with TestClient(_app(tmp_path)) as client:
        body = ask(client, "Tôi đã đặt cọc thuê nhà 20 triệu cho chủ nhà.")
    # MODE_2D's own response never carries the new trust-level fields --
    # this task must not alter the frozen deposit wire contract.
    assert body.get("trust_level") is None


def test_curated_traffic_question_gets_a_verified_trust_level(tmp_path: Path) -> None:
    with TestClient(_app(tmp_path)) as client:
        body = ask(client, "Tôi vượt đèn đỏ khi đi xe máy thì bị phạt bao nhiêu?")
    assert body["trust_level"] == "curated_verified"
    assert body["trust_label"] == "Đã kiểm chứng trong dữ liệu VietLaw"
    assert body["sources"], "a curated_verified answer must carry at least one source"


def test_out_of_scope_legal_question_gets_general_guidance_not_a_bare_scope_reply(
    tmp_path: Path,
) -> None:
    with TestClient(_app(tmp_path)) as client:
        body = ask(client, "Công ty giữ lương của tôi không trả thì tôi phải làm sao?")
    assert body["trust_level"] == "general_guidance"
    assert body["trust_label"] == "Hướng dẫn chung, chưa đủ căn cứ kết luận"
    # No invented article/clause/penalty -- checked structurally, not just by
    # the trust label: zero sources for a general-guidance answer.
    assert body["sources"] == []


def test_ordinary_non_legal_message_is_unaffected(tmp_path: Path) -> None:
    with TestClient(_app(tmp_path)) as client:
        body = ask(client, "cảm ơn nhé")
    assert body.get("trust_level") is None
    assert body["response_kind"] == "social"


# -- safety precedence (task §9) ---------------------------------------------

def test_unsafe_evasion_request_combined_with_traffic_wording_is_never_rescued(
    tmp_path: Path,
) -> None:
    # The exact phrase below is in the baseline unsafe_patterns.json
    # ("làm sao để không bị phạt") but not in FAST DEMO V2's own narrower
    # is_unsafe() keyword set -- this is precisely the gap the runtime-level
    # `state.classification.unsafe_intent_detected` gate closes. Without that
    # gate this would otherwise resolve to a real curated_verified answer.
    with TestClient(_app(tmp_path)) as client:
        body = ask(
            client,
            "Tôi vượt đèn đỏ khi đi xe máy, làm sao để không bị phạt?",
        )
    assert body.get("trust_level") is None
    assert body["sources"] == []


def test_explicit_unsafe_request_is_never_rescued_by_legal_fallback(tmp_path: Path) -> None:
    with TestClient(_app(tmp_path)) as client:
        body = ask(client, "Làm sao để xóa chứng cứ vi phạm giao thông của tôi?")
    assert body.get("trust_level") is None
    assert body["metadata"].get("unsafe") is True


def test_bribery_of_traffic_police_is_never_rescued_with_a_real_penalty_answer(
    tmp_path: Path,
) -> None:
    # Neither the baseline unsafe_patterns.json detector nor FAST DEMO V2's
    # own is_unsafe() covers bribery -- this is the gap
    # `legal_fallback_safety_guard.py` closes for this vertical specifically.
    with TestClient(_app(tmp_path)) as client:
        body = ask(
            client,
            "Tôi muốn đưa tiền cho cảnh sát giao thông để bỏ qua lỗi vượt đèn đỏ.",
        )
    assert body.get("trust_level") is None
    assert body["sources"] == []


# -- trust-level UI contract completeness (task §13.4) -----------------------

def test_curated_verified_response_carries_every_required_trust_field(tmp_path: Path) -> None:
    with TestClient(_app(tmp_path)) as client:
        body = ask(client, "Tôi không đội mũ bảo hiểm khi đi xe máy, mức phạt thế nào?")
    for field in ("trust_level", "trust_label", "trust_explanation"):
        assert body.get(field)


def test_general_guidance_response_carries_every_required_trust_field(tmp_path: Path) -> None:
    with TestClient(_app(tmp_path)) as client:
        body = ask(client, "Hàng xóm lấn chiếm đất của gia đình tôi thì phải làm sao?")
    for field in ("trust_level", "trust_label", "trust_explanation"):
        assert body.get(field)
    assert body["trust_level"] == "general_guidance"


def test_two_different_trust_levels_render_different_labels(tmp_path: Path) -> None:
    with TestClient(_app(tmp_path)) as client:
        curated = ask(client, "Tôi vượt đèn đỏ khi đi xe máy thì bị phạt bao nhiêu?")
        general = ask(client, "Hàng xóm lấn chiếm đất của gia đình tôi thì phải làm sao?", chat_id=None)
    assert curated["trust_label"] != general["trust_label"]


# -- chat-isolation (mirrors the existing MODE_2D invariant) -----------------

def test_traffic_matter_in_one_chat_is_invisible_to_a_new_chat(tmp_path: Path) -> None:
    with TestClient(_app(tmp_path)) as client:
        first = ask(client, "Tôi vượt đèn đỏ thì bị phạt bao nhiêu?")
        chat_id = first["chat_id"]
        ask(client, "Xe máy.", chat_id=chat_id)

        # A brand-new chat, same session: the pending-topic state must not
        # leak across chat_id boundaries.
        second = ask(client, "Xe máy.")
    assert second["chat_id"] != chat_id
    assert second.get("trust_level") is None


# -- Correction Round 1, M-01: attribution (end-to-end) ----------------------

def test_third_party_traffic_mention_answers_without_claiming_the_user_violated(
    tmp_path: Path,
) -> None:
    with TestClient(_app(tmp_path)) as client:
        # Both required facts (vehicle_type, signal_type) must be
        # determinable from this one message -- the impersonal path never
        # asks a personal follow-up. (Legal Correction Round 1 disabled
        # Rule D, phone use, which previously exercised this same shape.)
        body = ask(client, "Bạn tôi đi xe máy vượt đèn đỏ.")
    assert body.get("trust_level") == "curated_verified"
    blob = (body.get("summary") or "").lower()
    assert "bạn đã vi phạm" not in blob
    assert "bạn vi phạm" not in blob


def test_hypothetical_traffic_question_does_not_persist_as_a_user_matter(tmp_path: Path) -> None:
    with TestClient(_app(tmp_path)) as client:
        first = ask(client, "Nếu một người vượt đèn đỏ khi đi xe máy thì bị phạt sao?")
        chat_id = first["chat_id"]
        assert first.get("trust_level") == "curated_verified"

        # A later unrelated turn in the SAME chat must not resume as if the
        # hypothetical question had left a real pending traffic matter.
        second = ask(client, "Hôm nay thời tiết thế nào?", chat_id=chat_id)
    assert second.get("trust_level") is None
    assert second.get("response_kind") in ("social", "scope")


def test_negated_traffic_statement_does_not_receive_a_curated_penalty_answer(
    tmp_path: Path,
) -> None:
    with TestClient(_app(tmp_path)) as client:
        body = ask(client, "Tôi không vượt đèn đỏ.")
    assert body.get("trust_level") is None


# -- Correction Round 1, M-02: pending clarification release (end-to-end) ---

def test_unrelated_turn_after_pending_clarification_gets_normal_scope_reply(
    tmp_path: Path,
) -> None:
    with TestClient(_app(tmp_path)) as client:
        first = ask(client, "Tôi vượt đèn đỏ thì bị phạt bao nhiêu?")
        chat_id = first["chat_id"]
        assert first["clarifying_questions"] == ["Bạn điều khiển xe máy hay ô tô?"]

        second = ask(client, "Hôm nay thời tiết thế nào?", chat_id=chat_id)
    assert second.get("trust_level") is None
    assert "xe máy hay ô tô" not in " ".join(second.get("clarifying_questions") or [])


# -- Correction Round 2, M-02-R / Traffic Safe Subset V1: numeric/short
# clarification contamination and multi-field sequential clarification.
# The original regressions used the now-disabled speeding/alcohol/passenger/
# modification topics (task §2/§8); rebuilt here against Rule C (no_helmet,
# `traffic_no_helmet`), the enabled topic with the same "one required field
# still pending after the first fact is known" shape. (Legal Correction
# Round 1 disabled Rule D, phone use, which previously served this role.)

def test_numeric_unrelated_message_does_not_contaminate_a_later_labor_turn(
    tmp_path: Path,
) -> None:
    with TestClient(_app(tmp_path)) as client:
        first = ask(client, "Tôi lái xe máy nhưng quên mũ bảo hiểm.")
        chat_id = first["chat_id"]
        assert first["clarifying_questions"]

        second = ask(client, "Hôm nay 30 độ C.", chat_id=chat_id)
        assert second.get("trust_level") is None

        third = ask(
            client, "Tôi nhận lương tháng 7 thì công ty có trả đúng hạn không?", chat_id=chat_id
        )
    # The critical invariant: never no-helmet content for either turn.
    assert second.get("metadata", {}).get("legal_fallback_route") != "curated_traffic"
    assert third.get("trust_level") != "curated_verified"
    assert third.get("metadata", {}).get("legal_fallback_route") != "curated_traffic"


def test_short_answer_resolves_the_pending_no_helmet_topic(tmp_path: Path) -> None:
    with TestClient(_app(tmp_path)) as client:
        first = ask(client, "Tôi lái xe máy nhưng quên mũ bảo hiểm.")
        chat_id = first["chat_id"]
        second = ask(client, "Không đội mũ.", chat_id=chat_id)
    assert second["trust_level"] == "curated_verified"
    assert second["clarifying_questions"] == []


def test_multi_field_topic_asks_each_missing_field_across_separate_turns(tmp_path: Path) -> None:
    with TestClient(_app(tmp_path)) as client:
        first = ask(client, "Tôi đi xe máy nhưng quên mũ bảo hiểm.")
        chat_id = first["chat_id"]
        assert len(first["clarifying_questions"]) == 1

        second = ask(client, "Tôi.", chat_id=chat_id)
        # A clarification response's own `trust_level` is now None (Legal
        # Correction Round 1, MEDIUM-02) -- it carries no penalty/citation,
        # which is the actual invariant under test.
        assert len(second["clarifying_questions"]) == 1
        assert second["sources"] == []
        assert second.get("trust_level") is None

        third = ask(client, "Không đội mũ.", chat_id=chat_id)
    assert third["trust_level"] == "curated_verified"
    assert third["clarifying_questions"] == []


def test_disabled_topics_never_ask_a_clarification_or_resolve_as_curated(tmp_path: Path) -> None:
    # Task §2/§8: alcohol, speeding, driver_license, passenger_limit, and
    # vehicle_modification are all disabled pending legal correction -- none
    # may ever ask a follow-up clarification or return a specific penalty.
    # Legal Correction Round 1 (HIGH-01) added phone_use to this list.
    messages = [
        "Tôi có nồng độ cồn 0.3 mg/l khi đi xe máy thì bị phạt bao nhiêu?",
        "Tôi chạy quá tốc độ 10 km/h khi đi xe máy thì bị phạt bao nhiêu?",
        "Tôi quên mang bằng lái khi đi xe máy thì bị phạt bao nhiêu?",
        "Tôi chở 3 người trên xe máy thì bị phạt bao nhiêu?",
        "Tôi thay lốp nhỏ hơn quy định cho xe máy thì bị phạt bao nhiêu?",
        "Tôi dùng tay cầm điện thoại khi đang chạy xe máy.",
    ]
    with TestClient(_app(tmp_path)) as client:
        for message in messages:
            body = ask(client, message)
            assert body["clarifying_questions"] == [], message
            assert body.get("trust_level") == "general_guidance", message
            assert body["sources"] == [], message


def test_explicit_unknown_for_a_still_blocking_fact_falls_through_never_guesses(
    tmp_path: Path,
) -> None:
    # Task §7: a required (blocking) fact left unresolved even after an
    # explicit "I don't know" must never produce a curated answer.
    with TestClient(_app(tmp_path)) as client:
        first = ask(client, "Tôi lái xe máy nhưng quên mũ bảo hiểm.")
        chat_id = first["chat_id"]
        second = ask(client, "Tôi không biết.", chat_id=chat_id)
        assert second["clarifying_questions"] == []
        assert second["trust_level"] == "general_guidance"

        third = ask(client, "Công ty giữ lương của tôi thì phải làm sao?", chat_id=chat_id)
    assert third["trust_level"] == "general_guidance"
    assert third["sources"] == []
