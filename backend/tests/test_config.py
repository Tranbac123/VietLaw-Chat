"""Config + error taxonomy tests."""
import pytest

from app.config import Settings, SAFETY_NOTICE
from app.errors import (
    AiCoreError,
    InvalidRequest,
    ChatNotFound,
    RetrievalError,
    LlmError,
    InternalError,
)


def test_safety_notice_is_exact_spec_text():
    # Must match the backend-owned notice text byte-for-byte.
    assert SAFETY_NOTICE == (
        "Thông tin này chỉ mang tính định hướng ban đầu, không thay thế tư vấn "
        "pháp lý chính thức. Nếu vụ việc có tranh chấp lớn, rủi ro hình sự, "
        "quyền lợi quan trọng hoặc bạn không chắc nên làm gì, hãy tham khảo "
        "luật sư hoặc cơ quan chức năng."
    )


def test_settings_defaults(monkeypatch):
    monkeypatch.delenv("AI_BASE_URL", raising=False)
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    s = Settings(_env_file=None)
    assert s.ai_model_name == "api-model"
    assert s.min_content_score == 2
    assert s.top_k == 3
    assert s.max_results_absolute == 5
    assert s.history_window == 10
    assert s.llm_max_retries == 1


def test_provider_defaults_to_anthropic_without_base_url():
    s = Settings(_env_file=None, ai_base_url="")
    assert s.resolved_provider == "anthropic"


def test_provider_defaults_to_openai_when_base_url_set():
    s = Settings(_env_file=None, ai_base_url="http://localhost:1234/v1")
    assert s.resolved_provider == "openai"


def test_explicit_provider_wins_over_base_url_inference():
    s = Settings(_env_file=None, ai_provider="anthropic", ai_base_url="http://x/v1")
    assert s.resolved_provider == "anthropic"


@pytest.mark.parametrize(
    "exc,code,status",
    [
        (InvalidRequest, "invalid_request", 400),
        (ChatNotFound, "chat_not_found", 404),
        (RetrievalError, "retrieval_error", 503),
        (LlmError, "llm_error", 503),
        (InternalError, "internal_error", 500),
    ],
)
def test_error_taxonomy_code_and_status(exc, code, status):
    e = exc("boom")
    assert isinstance(e, AiCoreError)
    assert e.code == code
    assert e.http_status == status
    assert str(e) == "boom"
