from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend_lite.app.config import Settings
from backend_lite.app.constants import SAFETY_NOTICE
from backend_lite.app.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[2]

# Settings loads the repository `.env` into os.environ, so on a machine with a
# populated `.env` the demo flags and a live credential become visible to the
# whole test process. Without this guard the fast-demo orchestrator is wired
# into every create_app(), the suite makes real provider calls (slow, billable,
# non-deterministic), and baseline tests that expect the baseline pipeline to
# own the turn fail. Tests needing the orchestrator inject it explicitly, so
# clearing these here is safe.
_AMBIENT_PROVIDER_ENV = (
    "VIETLAW_FAST_DEMO_V2_ENABLED",
    "VIETLAW_DEMO_VERTICAL_SLICE_ENABLED",
    "VIETLAW_LLM_ENABLED",
    "VIETLAW_LLM_MODEL",
    "VIETLAW_LLM_PROVIDER",
    "VIETLAW_LLM_TIMEOUT_S",
    "VIETLAW_FAST_DEMO_TIMEOUT_S",
    "VIETLAW_FAST_DEMO_MAX_TOKENS",
    "VIETLAW_FAST_DEMO_STRUCTURED_OUTPUT",
    "ANTHROPIC_API_KEY",
)


@pytest.fixture(autouse=True)
def _isolate_provider_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every test hermetic with respect to ambient provider configuration."""

    for name in _AMBIENT_PROVIDER_ENV:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        backend_mode="lite",
        chat_db_path=tmp_path / "chat.sqlite3",
        legal_snippets_path=REPO_ROOT / "data" / "legal_snippets.json",
        unsafe_patterns_path=REPO_ROOT / "data" / "unsafe_patterns.json",
        cors_origins="http://127.0.0.1:5173,http://localhost:5173",
    )


@pytest.fixture
def app(settings: Settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def analyze_payload():
    def make(question: str, session_id: str = "session_test", **extra):
        return {
            "session_id": session_id,
            "question": question,
            "user_type": "citizen",
            "language": "vi",
            **extra,
        }

    return make


@pytest.fixture
def safety_notice() -> str:
    return SAFETY_NOTICE
