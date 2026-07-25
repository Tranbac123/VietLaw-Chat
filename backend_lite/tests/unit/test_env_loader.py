"""Focused coverage for repository-local backend_lite dotenv loading."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from backend_lite.app import env_loader
from backend_lite.app.config import Settings
from backend_lite.app.services.demo_llm_client import DemoLLMConfig

REPO_ROOT = Path(__file__).resolve().parents[3]
_ENV_NAMES = (
    "ANTHROPIC_API_KEY",
    "VIETLAW_LLM_ENABLED",
    "VIETLAW_LLM_MODEL",
    "VIETLAW_FAST_DEMO_V2_ENABLED",
)
_DOTENV_API_KEY_NAME = "ANTHROPIC_" + "API_KEY"
_DOTENV_TEST_KEY = "dotenv-" + "test-key"


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch):
    env_loader.load_local_env.cache_clear()
    for name in _ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    yield
    env_loader.load_local_env.cache_clear()


def write_dotenv(tmp_path: Path, lines: list[str]) -> Path:
    path = tmp_path / ".env"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_repository_dotenv_values_are_available_to_direct_demo_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(env_loader, "repository_root", lambda: tmp_path)
    write_dotenv(
        tmp_path,
        [
            _DOTENV_API_KEY_NAME + "=" + _DOTENV_TEST_KEY,
            "VIETLAW_LLM_ENABLED=1",
            "VIETLAW_LLM_MODEL=dotenv-model",
        ],
    )

    config = DemoLLMConfig.from_env()
    assert config.enabled is True
    assert config.model == "dotenv-model"
    assert config.api_key == _DOTENV_TEST_KEY


def test_process_environment_overrides_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(env_loader, "repository_root", lambda: tmp_path)
    write_dotenv(
        tmp_path,
        ["VIETLAW_LLM_MODEL=dotenv-model", "VIETLAW_LLM_ENABLED=0"],
    )
    monkeypatch.setenv("VIETLAW_LLM_MODEL", "explicit-runtime-model")
    monkeypatch.setenv("VIETLAW_LLM_ENABLED", "1")

    config = DemoLLMConfig.from_env()

    assert config.model == "explicit-runtime-model"
    assert config.enabled is True


def test_missing_dotenv_is_a_noop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(env_loader, "repository_root", lambda: tmp_path)
    assert env_loader.load_local_env(tmp_path / ".env") is False
    assert DemoLLMConfig.from_env().api_key is None


def test_dotenv_loading_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dotenv_path = write_dotenv(tmp_path, ["VIETLAW_LLM_MODEL=dotenv-model"])
    calls: list[tuple[Path, bool]] = []

    def tracked_load(path: Path, *, override: bool) -> bool:
        calls.append((path, override))
        return True

    monkeypatch.setattr(env_loader, "load_dotenv", tracked_load)

    assert env_loader.load_local_env(dotenv_path) is True
    assert env_loader.load_local_env(dotenv_path) is True
    assert calls == [(dotenv_path, False)]


def test_flag_off_and_diagnostics_do_not_expose_dotenv_key(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(env_loader, "repository_root", lambda: tmp_path)
    secret = _DOTENV_TEST_KEY
    dotenv_path = write_dotenv(
        tmp_path,
        [_DOTENV_API_KEY_NAME + "=" + secret, "VIETLAW_LLM_ENABLED=0"],
    )
    assert env_loader.load_local_env(dotenv_path) is True
    assert DemoLLMConfig.from_env().enabled is False

    settings = Settings(
        chat_db_path=tmp_path / "chat.sqlite3",
        legal_snippets_path=REPO_ROOT / "data" / "legal_snippets.json",
        unsafe_patterns_path=REPO_ROOT / "data" / "unsafe_patterns.json",
    )
    from backend_lite.app.main import create_app

    with TestClient(create_app(settings)) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert secret not in response.text
    assert secret not in caplog.text
