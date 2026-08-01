"""MODE_2B: proves the real HTTP transport bytes for `/api/analyze` are always
strict RFC-compatible JSON, regardless of what the model puts in a text field.

Context (see VIETLAW_FAST_DEMO_V2_MODE_2B_MALFORMED_JSON_CORRECTION_REPORT_V1.md):
a live MODE_2A checkpoint observed what first looked like a malformed JSON HTTP
response. The current reviewed application path (Anthropic adapter -> strict
`json.loads` -> `FastDemoPlan` validation -> `AnalyzeResponse` -> FastAPI/
Starlette serialization) produces strict valid JSON, and the MODE_2A
corruption signature is independently explained by the test operator's own
`RESP=$(curl ...); echo "$RESP" > file` shell capture, whose `echo` builtin
interprets backslash escape sequences (`\n` -> a real newline byte, `\\` -> a
single backslash) in the captured text -- not by any `backend_lite`
application code. No application code needed to change. These tests exist to
make the transport-safety guarantee permanent and regression-checked, using
`TestClient.content` (raw response bytes, not the `.json()` convenience
method) and zero live provider calls.
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
from backend_lite.app.services.fast_demo_source_pack import FastDemoSourcePack
from backend_lite.app.stores.fast_demo_state_store import FastDemoStateStore

REPO_ROOT = Path(__file__).resolve().parents[3]

PRIMARY_URL = "https://congbao.chinhphu.vn/van-ban/luat-so-91-2015-qh13-18397.htm"


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        backend_mode="lite",
        chat_db_path=tmp_path / "chat.sqlite3",
        legal_snippets_path=REPO_ROOT / "data" / "legal_snippets.json",
        unsafe_patterns_path=REPO_ROOT / "data" / "unsafe_patterns.json",
        cors_origins="http://127.0.0.1:5173",
    )


def _plan(**overrides) -> str:
    payload = {
        "response_kind": "legal",
        "response_mode": "guidance",
        "summary": "Đã ghi nhận thông tin của bạn.",
        "analysis": None,
        "clarifying_questions": [],
        "checklist": [],
        "next_steps": [],
        "draft": None,
        "known_facts_summary": [],
        "uncertainty_notice": None,
        "fact_updates": [],
        "selected_source_ids": ["civil_deposit_001"],
    }
    payload.update(overrides)
    # ensure_ascii=False mirrors real model output: the provider is not asked
    # to \u-escape Vietnamese characters, only to escape JSON control chars.
    return json.dumps(payload, ensure_ascii=False)


def _build(tmp_path: Path, responses: list[str]):
    settings = _settings(tmp_path)
    app = create_app(settings)
    container = app.state.container
    fake = FakeLLMClient(responses=list(responses))
    store = FastDemoStateStore(settings.chat_db_path)
    store.ensure_schema()
    container.runtime.fast_demo_orchestrator = FastDemoOrchestrator(
        store=store,
        source_pack=FastDemoSourcePack.from_snippets(container.snippet_store.active_snippets()),
        llm_client=fake,
        config=FastDemoConfig(
            enabled=True, model="claude-test-model", api_key="test-key",
            timeout_s=30.0, max_output_tokens=2048, temperature=0.0,
        ),
    )
    return app, fake


def _ask(client: TestClient, question: str, session: str = "s1"):
    return client.post("/api/analyze", json={"session_id": session, "question": question})


# ---------------------------------------------------------------------------
# 1/3/4/5: a well-formed model plan whose analysis field legitimately contains
# a real paragraph break, quotes, a backslash, and Vietnamese text -- the
# transport bytes must remain strict JSON and the round-tripped value must
# still contain the intended paragraph break.
# ---------------------------------------------------------------------------

MULTILINE_ANALYSIS = (
    'Dòng phân tích thứ nhất.\n\n'
    'Dòng thứ hai có "trích dẫn" và một dấu \\ gạch chéo ngược, '
    'kèm chữ có dấu: đặt cọc, Điều 328.'
)


def test_multiline_quotes_backslash_and_unicode_survive_strict_json_transport(tmp_path: Path) -> None:
    app, fake = _build(tmp_path, [_plan(analysis=MULTILINE_ANALYSIS)])
    with TestClient(app) as client:
        response = _ask(client, "Tôi đã đặt cọc 20 triệu để thuê nhà nhưng chủ nhà không giao nhà.")

    assert response.status_code == 200
    raw = response.content  # raw HTTP body bytes, not the parsed convenience accessor

    # (5) strict json.loads() must succeed on the raw transport bytes.
    body = json.loads(raw)

    # (1)/(2)/(3) newline, quotes, backslash and Vietnamese diacritics must
    # all still be present, exactly, after a real HTTP round trip.
    assert body["analysis"] == MULTILINE_ANALYSIS
    assert "\n\n" in body["analysis"]
    assert '"trích dẫn"' in body["analysis"]
    assert "\\ gạch chéo ngược" in body["analysis"]

    # The literal escape sequence must appear in the wire bytes as the
    # two-character JSON escape, never as a bare control byte -- located
    # within the `"analysis":"..."` field specifically, not scanned across
    # the whole body (a bare 0x0A byte would still be legal JSON whitespace
    # *between* tokens elsewhere, so that broader claim is not asserted here).
    analysis_field_start = raw.index(b'"analysis":"')
    analysis_field_end = raw.index(b'","draft"', analysis_field_start)
    analysis_field_bytes = raw[analysis_field_start:analysis_field_end]
    assert b"\\n\\n" in analysis_field_bytes
    assert b"\n" not in analysis_field_bytes

    # (9) exactly one provider call -- serialization causes no extra calls.
    assert fake.calls == 1


# ---------------------------------------------------------------------------
# 6: malformed provider-structured output (the model's own raw text containing
# a bare, unescaped control character) must follow the existing controlled
# fallback path -- never crash, never partially serialize, never leak an
# invalid byte into the transport JSON.
# ---------------------------------------------------------------------------

def test_malformed_provider_json_falls_back_and_transport_stays_valid(tmp_path: Path) -> None:
    # The model's own text is invalid JSON: a bare literal newline inside a
    # string value, which `json.loads` rejects (RFC 8259 requires \n here).
    malformed_model_text = (
        '{"response_kind":"legal","response_mode":"guidance",'
        '"summary":"dong 1\ndong 2","analysis":null,"clarifying_questions":[],'
        '"checklist":[],"next_steps":[],"draft":null,"known_facts_summary":[],'
        '"uncertainty_notice":null,"fact_updates":[],'
        '"selected_source_ids":["civil_deposit_001"]}'
    )
    app, fake = _build(tmp_path, [malformed_model_text])
    with TestClient(app) as client:
        response = _ask(client, "Tôi đã đặt cọc 20 triệu để thuê nhà nhưng chủ nhà không giao nhà.")

    assert response.status_code == 200
    raw = response.content
    body = json.loads(raw)  # must still succeed: the fallback path is used, not a crash

    # The controlled deterministic fallback contract, not fabricated legal
    # content: no clarifying question, checklist entry or next step invents
    # anything the model didn't legitimately provide, and the raw invalid
    # model text never reaches the summary/analysis fields verbatim.
    assert malformed_model_text not in body["summary"]
    assert body["analysis"] is None
    assert fake.calls == 1  # exactly one call was attempted; no retry, no repair call


# ---------------------------------------------------------------------------
# 7/8: unchanged existing behavior -- normal legal answers keep the correct
# official source, and a source-less answer stays source-less.
# ---------------------------------------------------------------------------

def test_normal_legal_response_still_carries_the_official_source(tmp_path: Path) -> None:
    app, fake = _build(tmp_path, [_plan()])
    with TestClient(app) as client:
        response = _ask(client, "Tôi đã đặt cọc 20 triệu để thuê nhà nhưng chủ nhà không giao nhà.")

    body = json.loads(response.content)
    urls = [s["url"] for s in body["sources"]]
    assert PRIMARY_URL in urls
    assert fake.calls == 1


def test_sourceless_response_still_has_no_sources(tmp_path: Path) -> None:
    app, fake = _build(tmp_path, [_plan(selected_source_ids=[])])
    with TestClient(app) as client:
        response = _ask(client, "Tôi đã đặt cọc 20 triệu để thuê nhà nhưng chủ nhà không giao nhà.")

    body = json.loads(response.content)
    assert body["sources"] == []
    assert fake.calls == 1


# ---------------------------------------------------------------------------
# 10: existing deterministic routes are unaffected by any of the above --
# still zero provider calls, still valid transport JSON.
# ---------------------------------------------------------------------------

def test_deterministic_route_unaffected_and_still_valid_json(tmp_path: Path) -> None:
    app, fake = _build(tmp_path, [])
    with TestClient(app) as client:
        response = _ask(client, "hello")

    assert response.status_code == 200
    body = json.loads(response.content)
    assert body["metadata"]["fast_demo_route"] == "social"
    assert fake.calls == 0
