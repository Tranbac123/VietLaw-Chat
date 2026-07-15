"""LLM client — provider dispatch, retry-once, LlmError. No network (injected transport)."""
import pytest

from app.config import Settings
from app.errors import LlmError
from app.llm_client import LLMClient


def _client(transport):
    return LLMClient(Settings(_env_file=None, ai_provider="anthropic", ai_api_key="k",
                              llm_max_retries=1), transport=transport)


def test_generate_returns_transport_output():
    assert _client(lambda p: "hello").generate("prompt") == "hello"


def test_retries_once_then_succeeds():
    calls = {"n": 0}

    def flaky(prompt):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutError("boom")
        return "ok"

    assert _client(flaky).generate("p") == "ok"
    assert calls["n"] == 2


def test_raises_llm_error_after_retries_exhausted():
    def always_fail(prompt):
        raise TimeoutError("down")

    with pytest.raises(LlmError):
        _client(always_fail).generate("p")
