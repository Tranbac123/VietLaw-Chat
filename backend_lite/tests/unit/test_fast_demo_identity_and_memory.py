"""PHASE C CORRECTION §4: bounded deterministic identity/memory routing.

Confirmed via the owner browser checkpoint: the fixture backend's own
deterministic social/capability routing (not the scripted LLM plan) answered
`hello` by immediately demanding rental-deposit facts, answered `bạn là ai` the
same way, and had no route at all for `tôi là ai` / `bạn nhớ gì về tôi` --
both fell through to the generic out-of-scope template. This is real backend
routing/copy, shared by MODE_1 and MODE_2 alike; none of it is provider output,
so every assertion here is deterministic and makes zero provider calls.

Scope discipline: this does not attempt to make the demo an intelligent agent.
Memory answers are built only from facts already accepted into the current
chat's state (the same `_known_facts` helper the existing fallback copy uses),
never invented, never claiming cross-chat memory.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend_lite.app.config import Settings
from backend_lite.app.main import create_app
from backend_lite.app.services.demo_llm_client import FakeLLMClient
from backend_lite.app.services.fast_demo_orchestrator import (
    FastDemoConfig,
    FastDemoOrchestrator,
)
from backend_lite.app.services.fast_demo_routing import (
    CAPABILITY_TEXT,
    GREETING_TEXT,
    USER_IDENTITY_TEXT,
    FastDemoRoute,
    classify_route,
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


DEPOSIT_PLAN = plan(
    summary="Đã ghi nhận 20 triệu.",
    fact_updates=[
        {"operation": "set", "slot": "deposit_amount", "value": 20000000,
         "evidence_quote": "20 triệu"},
    ],
)


def build(tmp_path: Path, responses: list[str]):
    settings = _settings(tmp_path)
    app = create_app(settings)
    container = app.state.container
    fake = FakeLLMClient(responses=list(responses))
    state_store = FastDemoStateStore(settings.chat_db_path)
    state_store.ensure_schema()
    container.runtime.fast_demo_orchestrator = FastDemoOrchestrator(
        store=state_store,
        source_pack=FastDemoSourcePack.from_snippets(container.snippet_store.active_snippets()),
        llm_client=fake,
        config=FastDemoConfig(
            enabled=True, model="claude-test-model", api_key="test-key",
            timeout_s=30.0, max_output_tokens=2048, temperature=0.0,
        ),
    )
    return app, fake, state_store, settings.chat_db_path


def ask(client: TestClient, question: str, *, chat_id: str | None = None, session: str = "s1") -> dict:
    payload = {"session_id": session, "question": question}
    if chat_id:
        payload["chat_id"] = chat_id
    response = client.post("/api/analyze", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def test_user_identity_is_a_distinct_route_from_capability() -> None:
    assert classify_route("tôi là ai", has_active_matter=False) is FastDemoRoute.USER_IDENTITY
    assert classify_route("bạn là ai", has_active_matter=False) is FastDemoRoute.CAPABILITY


def test_memory_query_is_its_own_route() -> None:
    assert classify_route("bạn nhớ gì về tôi", has_active_matter=False) is FastDemoRoute.MEMORY
    assert classify_route("bạn biết gì về tôi", has_active_matter=False) is FastDemoRoute.MEMORY


def test_neither_new_route_is_absorbed_by_scope_or_acknowledgment() -> None:
    for text in ("tôi là ai", "bạn nhớ gì về tôi", "bạn biết gì về tôi"):
        route = classify_route(text, has_active_matter=False)
        assert route not in (FastDemoRoute.SCOPE_OR_UNSUPPORTED, FastDemoRoute.ACKNOWLEDGMENT)


# ---------------------------------------------------------------------------
# Greeting / capability copy
# ---------------------------------------------------------------------------

def test_greeting_does_not_immediately_demand_rental_facts() -> None:
    lowered = GREETING_TEXT.lower()
    assert "số tiền" not in lowered
    assert "chứng từ" not in lowered
    assert "vietlaw" in lowered


def test_capability_discloses_scope_without_pretending_to_know_the_user() -> None:
    lowered = CAPABILITY_TEXT.lower()
    assert "vietlaw" in lowered
    assert "tiền cọc" in CAPABILITY_TEXT  # existing regression: must stay present
    assert "bản demo" not in lowered
    assert "bạn là" not in lowered  # never asserts anything about who the user is


def test_greeting_route_end_to_end(tmp_path: Path) -> None:
    app, fake, _, _ = build(tmp_path, [])
    with TestClient(app) as client:
        body = ask(client, "hello")
    assert body["metadata"]["fast_demo_route"] == "social"
    assert body["summary"] == GREETING_TEXT
    assert fake.calls == 0


# ---------------------------------------------------------------------------
# User identity
# ---------------------------------------------------------------------------

def test_user_identity_route_end_to_end(tmp_path: Path) -> None:
    app, fake, _, _ = build(tmp_path, [])
    with TestClient(app) as client:
        body = ask(client, "tôi là ai")
    assert body["metadata"]["fast_demo_route"] == "user_identity"
    assert body["summary"] == USER_IDENTITY_TEXT
    assert fake.calls == 0
    # Never claims to recognize the user, and never mutates rental facts.
    assert "tôi chưa biết" in body["summary"].lower()


def test_user_identity_is_never_answered_with_the_rental_template(tmp_path: Path) -> None:
    app, _, _, _ = build(tmp_path, [])
    with TestClient(app) as client:
        body = ask(client, "tôi là ai")
    assert "tiền cọc" not in body["summary"].lower()


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

def test_memory_query_with_no_facts_says_so_honestly(tmp_path: Path) -> None:
    app, fake, _, _ = build(tmp_path, [])
    with TestClient(app) as client:
        body = ask(client, "bạn nhớ gì về tôi")
    assert body["metadata"]["fast_demo_route"] == "memory"
    assert fake.calls == 0
    lowered = body["summary"].lower()
    assert "chưa ghi nhận" in lowered
    assert "tiền cọc" not in lowered  # not the rental template either


def test_memory_query_reports_only_facts_already_in_this_chat(tmp_path: Path) -> None:
    app, fake, state_store, _ = build(tmp_path, [DEPOSIT_PLAN, plan()])
    with TestClient(app) as client:
        first = ask(client, "tôi đã đặt cọc 20 triệu cho chủ nhà")
        chat_id = first["chat_id"]
        memory = ask(client, "bạn nhớ gì về tôi", chat_id=chat_id)

    assert memory["metadata"]["fast_demo_route"] == "memory"
    assert "20.000.000" in memory["summary"]
    # Exactly what _known_facts would report -- nothing invented beyond it.
    known = state_store.load(chat_id).state.facts
    assert known.deposit_amount is not None


def test_memory_query_never_invents_a_fact_that_was_not_accepted(tmp_path: Path) -> None:
    app, _, _, _ = build(tmp_path, [])
    with TestClient(app) as client:
        body = ask(client, "bạn nhớ gì về tôi")
    for invented in ("triệu", "chưa bàn giao", "chủ nhà"):
        assert invented not in body["summary"]


def test_memory_query_does_not_mutate_state(tmp_path: Path) -> None:
    app, _, state_store, _ = build(tmp_path, [DEPOSIT_PLAN])
    with TestClient(app) as client:
        first = ask(client, "tôi đã đặt cọc 20 triệu cho chủ nhà")
        chat_id = first["chat_id"]
        before = state_store.load(chat_id)
        ask(client, "bạn nhớ gì về tôi", chat_id=chat_id)
        after = state_store.load(chat_id)

    assert after.state_version == before.state_version
    assert after.state.model_dump() == before.state.model_dump()


# ---------------------------------------------------------------------------
# Social turns never clear or contaminate existing facts
# ---------------------------------------------------------------------------

def test_greeting_and_capability_mid_chat_preserve_existing_facts(tmp_path: Path) -> None:
    app, _, state_store, _ = build(tmp_path, [DEPOSIT_PLAN])
    with TestClient(app) as client:
        first = ask(client, "tôi đã đặt cọc 20 triệu cho chủ nhà")
        chat_id = first["chat_id"]
        before = state_store.load(chat_id)

        for text in ("xin chào", "bạn làm được gì", "tôi là ai", "bạn nhớ gì về tôi"):
            ask(client, text, chat_id=chat_id)

        after = state_store.load(chat_id)

    assert after.state_version == before.state_version
    assert after.state.facts.deposit_amount.value == 20000000
