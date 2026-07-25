"""FAST DEMO V2 provider-failure diagnostics and controlled fallback.

The live defect was not that the fallback existed — it was that every failure
collapsed to one opaque reason (`plan_unavailable`), so a misconfigured request
parameter was indistinguishable from an unconfigured provider. These tests pin
the reason categories and prove no credential ever reaches them.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend_lite.app.config import Settings
from backend_lite.app.contracts.demo_llm import LLMErrorKind
from backend_lite.app.main import create_app
from backend_lite.app.services.demo_llm_client import FakeLLMClient
from backend_lite.app.services.fast_demo_orchestrator import (
    FastDemoConfig,
    FastDemoOrchestrator,
)
from backend_lite.app.services.fast_demo_source_pack import FastDemoSourcePack
from backend_lite.app.stores.fast_demo_state_store import FastDemoStateStore

REPO_ROOT = Path(__file__).resolve().parents[3]

# Assembled at runtime so no literal matching a real credential's shape ever
# appears in the source tree (a hard-coded one trips secret scanners in CI).
_PREFIX = "sk" + "-ant"
SECRET = f"{_PREFIX}-fake-key-for-leak-assertions-0000000000"


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        backend_mode="lite",
        chat_db_path=tmp_path / "chat.sqlite3",
        legal_snippets_path=REPO_ROOT / "data" / "legal_snippets.json",
        unsafe_patterns_path=REPO_ROOT / "data" / "unsafe_patterns.json",
        cors_origins="http://127.0.0.1:5173",
    )


def build(tmp_path: Path, fake: FakeLLMClient, **overrides):
    app = create_app(_settings(tmp_path))
    container = app.state.container
    store = FastDemoStateStore(_settings(tmp_path).chat_db_path)
    store.ensure_schema()
    config_kwargs = {
        "enabled": True,
        "model": "claude-sonnet-4-6",
        "api_key": SECRET,
        "timeout_s": 30.0,
        "max_output_tokens": 2048,
        "temperature": 0.0,
    }
    config_kwargs.update(overrides)
    container.runtime.fast_demo_orchestrator = FastDemoOrchestrator(
        store=store,
        source_pack=FastDemoSourcePack.from_snippets(container.snippet_store.active_snippets()),
        llm_client=fake,
        config=FastDemoConfig(**config_kwargs),
    )
    return app


def ask(client: TestClient, question: str, crid: str) -> dict:
    response = client.post(
        "/api/analyze",
        json={
            "session_id": "diag",
            "question": question,
            "user_type": "citizen",
            "language": "vi",
            "client_request_id": crid,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


LEGAL = "Tôi đã đặt cọc thuê nhà 20 triệu và có sao kê chuyển khoản."


# -- 8/9: each failure mode yields its own safe reason category -------------

@pytest.mark.parametrize(
    ("fake", "expected_prefix"),
    [
        (FakeLLMClient(error=LLMErrorKind.PROVIDER_ERROR), "provider_error:"),
        (FakeLLMClient(error=LLMErrorKind.TIMEOUT), "provider_error:"),
        (FakeLLMClient(error=LLMErrorKind.REFUSAL), "provider_error:"),
        (FakeLLMClient(responses=["definitely not json"]), "provider_invalid_json"),
        (FakeLLMClient(responses=["[]"]), "provider_invalid_json"),
        (FakeLLMClient(responses=['{"response_kind": "legal"}']), "local_schema_validation_failure"),
    ],
)
def test_each_failure_mode_reports_its_own_category(
    tmp_path: Path, fake: FakeLLMClient, expected_prefix: str
) -> None:
    app = build(tmp_path, fake)
    with TestClient(app) as client:
        body = ask(client, LEGAL, "f-1")

    reason = body["metadata"]["reason"]
    assert reason.startswith(expected_prefix), reason
    # Exactly one call: no hidden retry, no repair call.
    assert fake.calls == 1


def test_unconfigured_provider_is_distinguishable_from_a_failed_call(tmp_path: Path) -> None:
    fake = FakeLLMClient()
    app = build(tmp_path, fake, api_key=None)
    with TestClient(app) as client:
        body = ask(client, LEGAL, "f-2")

    # The old code reported "plan_unavailable" for this AND for a failed call.
    assert body["metadata"]["reason"] == "provider_not_configured"
    assert fake.calls == 0


def test_diagnostics_never_leak_the_credential(tmp_path: Path) -> None:
    fake = FakeLLMClient(error=LLMErrorKind.PROVIDER_ERROR)
    app = build(tmp_path, fake)
    with TestClient(app) as client:
        body = ask(client, LEGAL, "f-3")

    serialized = json.dumps(body, ensure_ascii=False)
    assert SECRET not in serialized
    assert _PREFIX not in serialized
    assert "x-api-key" not in serialized.lower()
    assert "authorization" not in serialized.lower()
    # A category is present, but no raw provider payload.
    assert body["metadata"]["reason"]


def test_fallback_copy_is_user_facing_not_technical(tmp_path: Path) -> None:
    app = build(tmp_path, FakeLLMClient(error=LLMErrorKind.PROVIDER_ERROR))
    with TestClient(app) as client:
        body = ask(client, LEGAL, "f-4")

    summary = body["summary"]
    assert "phản hồi dự phòng" not in summary.lower()
    assert "provider" not in summary.lower()
    assert "giữ lại" in summary
    # The user still gets something actionable rather than a dead end.
    assert body["next_steps"]
    assert body["uncertainty_notice"]
    assert "dự phòng" not in body["uncertainty_notice"].lower()


# -- structured-output toggle reaches the client ---------------------------

def test_structured_output_flag_is_passed_through(tmp_path: Path) -> None:
    fake = FakeLLMClient(error=LLMErrorKind.PROVIDER_ERROR)
    app = build(tmp_path, fake, use_structured_output=False)
    with TestClient(app) as client:
        ask(client, LEGAL, "f-5")
    assert fake.last_use_structured_output is False

    fake2 = FakeLLMClient(error=LLMErrorKind.PROVIDER_ERROR)
    app2 = build(tmp_path / "b", fake2, use_structured_output=True)
    with TestClient(app2) as client:
        ask(client, LEGAL, "f-6")
    assert fake2.last_use_structured_output is True


def test_anthropic_client_omits_output_config_when_unsupported() -> None:
    """The actual request payload must not carry output_config for a model that
    rejects it — this is the root cause of the live fallback."""

    import httpx

    from backend_lite.app.services.demo_llm_client import AnthropicLLMClient, DemoLLMConfig

    captured: dict = {}

    class _Transport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            captured.update(json.loads(request.content))
            return httpx.Response(
                200, json={"stop_reason": "end_turn", "content": [{"type": "text", "text": "{}"}]}
            )

    config = DemoLLMConfig(
        enabled=True, provider="anthropic", model="claude-sonnet-4-6",
        timeout_s=5.0, api_key=SECRET,
    )
    client = AnthropicLLMClient(config)

    import asyncio

    original = httpx.AsyncClient

    def _patched(*args, **kwargs):
        kwargs["transport"] = _Transport()
        return original(*args, **kwargs)

    httpx.AsyncClient = _patched  # type: ignore[misc]
    try:
        asyncio.run(
            client.complete(
                system="s", user="u", max_tokens=64, timeout_s=5.0,
                json_schema={"type": "object"}, temperature=0.0,
                use_structured_output=False,
            )
        )
    finally:
        httpx.AsyncClient = original  # type: ignore[misc]

    assert "output_config" not in captured
    assert captured["model"] == "claude-sonnet-4-6"
    assert captured["temperature"] == 0.0
